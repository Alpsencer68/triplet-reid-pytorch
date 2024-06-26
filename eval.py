import torch
from torch.utils.data import DataLoader
from sklearn.metrics import precision_recall_curve, auc, roc_curve
from sklearn.metrics import confusion_matrix
import numpy as np
import seaborn as sns
import argparse

from triplet_selector import PairSelector
from batch_sampler import BatchSampler
from datasets.Market1501 import Market1501
from logger import logger
import matplotlib.pyplot as plt
from pathlib import Path

import utils

def visualize_results(preds, pair_labels, indices, imgs):
    K = 5

    # Get the indices of the pairs where the pair labels are 0
    print("pair_labels.size", pair_labels.shape)
    equal_pairs_indices = [i for i, label in enumerate(pair_labels) if label == 1.]

    selected_pairs_indices = equal_pairs_indices[:K]

    # Create a new figur
    _, axs = plt.subplots(K, 3, figsize=(10, K*5))

    mean = np.array([0.485, 0.456, 0.406])
    std = np.array([0.229, 0.224, 0.225])

    for i, pair_index in enumerate(selected_pairs_indices):
        pred = preds[pair_index]

        # Get the indices of the images in the pair
        img_i, img_j = indices[pair_index]
        img1 = imgs[img_i].cpu().numpy().transpose((1, 2, 0))  # Transpose to (height, width, channels)
        img2 = imgs[img_j].cpu().numpy().transpose((1, 2, 0))  # Transpose to (height, width, channels)

        img1 = std * img1 + mean
        img2 = std * img2 + mean

        # Plot the images and the prediction
        axs[i, 0].imshow(img1)
        axs[i, 0].set_title(f"Image {img_i}")
        axs[i, 0].axis('off')

        axs[i, 1].imshow(img2)
        axs[i, 1].set_title(f"Image {img_j}")
        axs[i, 1].axis('off')

        prediction_text = "same" if pred == 1 else "different"
        axs[i, 2].text(0.5, 0.5, f"Model prediction: {prediction_text}\n", 
                    horizontalalignment='center', verticalalignment='center')
        axs[i, 2].axis('off')

    # Display the figure
    plt.tight_layout()
    plt.savefig("results.png")
    plt.show()


def calculate_g_prime(vector, vectors, labels):
    distances = torch.sqrt(torch.sum((vectors - vector)**2, dim=1)) # euclidian distance
    
    sorted_indices = torch.argsort(distances)  # Get indices that sort distances
    
    # Sort vectors and labels based on sorted indices
    sorted_vectors = vectors[sorted_indices]
    sorted_labels = labels[sorted_indices]
    
    return sorted_vectors, sorted_labels


def average_precision_at_k(label, labels, k):
    num_relevant = 0
    precision_sum = 0.0
    for i in range(min(k, len(labels))):
        if labels[i] == label:
            num_relevant += 1
            precision_sum += num_relevant / (i + 1)
    if num_relevant == 0:
        return 0
    return precision_sum / num_relevant


def map_at_k(lbs, labels_sorted, k):
    total_ap = 0.0
    for label, labels in zip(lbs, labels_sorted):
        total_ap += average_precision_at_k(label, labels, k)
    return total_ap / len(lbs)

def cmc_curve(labels, labels_sorted):
    num_queries =  min(len(labels_sorted[0]), 20)
    num_matches = torch.zeros(num_queries)
    ranks = []

    for i in range(num_queries):
        for j in range(1, min(len(labels_sorted[i]), 20)):
            if labels_sorted[i][j] == labels[i]:
                num_matches[j] += 1
                ranks.append(j + 1)
                break

    cmc = num_matches.cumsum(0) / num_queries
    print(num_matches)
    return cmc, ranks

def eval(args):
    if args.dataset_dir is None:
        print('Please provide a dataset directory')
        exit()
    if args.all_dir is None:

        if args.ae_dir is None or args.ae_type is None:
            print('Please provide an autoencoder for evaluation')
            exit()
        if args.classifier_dir is None:
            print('Please provide a classifier for evaluation')
            exit()
        if args.backbone_dir is None or args.backbone_type is None:
            print('Please provide a backbone for evaluation')
            exit()
        
        ae_dir = args.ae_dir
        backbone_dir = args.backbone_dir
        classifier_dir = args.classifier_dir

    else:
        all_dir = Path(args.all_dir)
        ae_dir = all_dir / "best_ae.pkl"
        backbone_dir = all_dir / "best_backbone.pkl"
        classifier_dir = all_dir / "best_classifier.pkl"

    backbone_type = args.backbone_type
    ae_type = args.ae_type
    dataset_dir = args.dataset_dir
    
    backbone, ae, classifier = utils.load_model(backbone_type, backbone_dir, classifier_dir, ae_dir, ae_type)



    backbone.eval()
    ae.eval()
    classifier.eval()
    
    pair_selector = PairSelector()
    ds = Market1501(dataset_dir, is_train = True, use_swin = (backbone_type == "swin"))
    sampler = BatchSampler(ds, 18, 5)
    dl = DataLoader(ds, batch_sampler = sampler, num_workers = 4)
    
    diter = iter(dl)
    with torch.inference_mode():
        try:
            imgs, lbs, _ = next(diter)
        except StopIteration:
            diter = iter(dl)
            imgs, lbs, _ = next(diter)
            
        imgs = imgs.cuda() # images
        lbs = lbs.cuda() # corresponding id labels
    
        backbone_output = backbone(imgs)

        if (ae_type == 'vae'):
                _, embeds, _, _= ae(backbone_output)
        else:
            _, embeds = ae(backbone_output)

        same_pairs, diff_pairs, pair_indices = pair_selector(embeds, lbs, 18, 5)
        size = same_pairs.shape[0]

        same_pair_indices = pair_indices[:size]
        diff_pair_indices = pair_indices[size:]

        diff_pairs = diff_pairs[:size]
        diff_pair_indices = diff_pair_indices[:size]

        pair_indices = same_pair_indices + diff_pair_indices

        pairs = torch.cat((same_pairs, diff_pairs), dim=0)
        pair_labels = torch.cat((torch.ones(size), torch.zeros(size)), dim=0)
        preds = classifier(pairs)
        preds = preds.cpu().detach().numpy()
        preds_thresholded = np.where(preds > 0.7, 1, 0) # thresholding with 0.7

        visualize_results(preds_thresholded, pair_labels, pair_indices, imgs)


        # create rankings for each query
        g_primes = []
        labels_list = []
        for embed in embeds:
            # sort wrt distance
            g_prime, labels = calculate_g_prime(embed, embeds, lbs)
            g_primes.append([g_prime, labels])
            labels_list.append(labels)

        k = 5
            
        # calculate Rank@1
        rank1 = map_at_k(lbs, labels_list, 1)
        print(f"Rank@5:{rank1}")

        # calculate mAP@5
        map5 = map_at_k(lbs, labels_list, k) 
        print(f"mAP@5:{map5}")
        
        # calculate confusion matrix
        cm = confusion_matrix(pair_labels.cpu().numpy(), preds > 0.5)
        print(cm)

        TN, FP = cm[0]
        FN, TP = cm[1]
        
        print(f"TP: {TP}, FP: {FP}, FN: {FN}, TN: {TN}")
        
        labels = np.array([['TP: ' + str(TP), 'FP: ' + str(FP)], ['FN: ' + str(FN), 'TN: ' + str(TN)]])

        plt.figure(figsize=(10,7))
        sns.heatmap([[TP, FP],[FN, TN]], annot=labels, fmt='', cmap='Blues')
        plt.xlabel('Actual')
        plt.ylabel('Predicted')
        plt.xticks([0.5, 1.5], ['1', '0'])
        plt.yticks([0.5, 1.5], ['1', '0'], rotation=0)
        plt.savefig("Confusion.png")
        plt.show()
        
        # Calculate and print accuracy
        accuracy = (TP + TN) / (TP + TN + FP + FN) if (TP + TN + FP + FN) != 0 else 0.
        print(f"Accuracy: {accuracy}")

        # Calculate and print precision
        precision = TP / (TP + FP) if (TP + FP)  != 0 else 0.
        print(f"Precision: {precision}")

        # Calculate and print recall
        recall = TP / (TP + FN) if (TP + FN) != 0 else 0.
        print(f"Recall: {recall}")

        # Calculate and print F1 score
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) != 0 else 0.
        print(f"F1 Score: {f1_score}")

        # Calculate and print F2 score
        beta = 2
        f2_score = (1 + beta**2) * (precision * recall) / ((beta**2 * precision) + recall) if  ((beta**2 * precision) + recall) != 0 else 0.
        print(f"F2 Score: {f2_score}")
        
        with open('metrics.txt', 'w') as f:
            # Write each metric to the file
            f.write(f"Accuracy: {accuracy}\n")
            f.write(f"Precision: {precision}\n")
            f.write(f"Recall: {recall}\n")
            f.write(f"F1 Score: {f1_score}\n")
            f.write(f"F2 Score: {f2_score}\n")
            f.write(f"Rank1: {rank1}\n")
            f.write(f"mAP5: {map5}\n")

        #Precision Recall Curve
        precision, recall, _ = precision_recall_curve(pair_labels.cpu().numpy(), preds)
        auc_pr = auc(recall, precision)
        plt.plot(recall, precision, label=f'PR curve (AUC = {auc_pr:.2f})')
        plt.xlabel('Recall')
        plt.ylabel('Precision')
        plt.title('Precision-Recall Curve')
        plt.legend()
        plt.grid(True)
        plt.savefig("Precision-Recall.png")
        plt.show()

        #CMC Curve 
        cmc, ranks = cmc_curve(lbs.cpu().numpy(), labels_list)
        plt.figure()
        plt.plot(np.arange(1, len(cmc) + 1), cmc)
        plt.xlabel('Rank')
        plt.ylabel('Matching Probability')
        plt.title('Cumulative Matching Characteristics (CMC) Curve')
        plt.grid(True)
        plt.savefig("CMC.png")
        plt.show()

        # ROC Curve
        fpr, tpr, thresholds = roc_curve(pair_labels.cpu().numpy(), preds)
        auc_pr = auc(fpr, tpr)
        plt.figure()
        plt.plot(fpr, tpr, label=f'ROC curve (AUC = {auc_pr:.2f})')
        plt.xlabel('FP')
        plt.ylabel('TP')
        plt.title('ROC Curve')
        plt.grid(True)
        plt.legend()
        plt.savefig("ROC.png")
        plt.show()

        
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--backbone_dir', type=str, default=None, help='backbone weights directory')
    parser.add_argument('--backbone_type', type=str, default=None, help='backbone name')
    parser.add_argument('--classifier_dir', type=str, default=None, help='Autoencoder weights')
    parser.add_argument('--ae_dir', type=str, default=None, help='autoencoder weights')
    parser.add_argument('--ae_type', type=str, default=None, help='autoencoder type')
    parser.add_argument('--dataset_dir', type=str, default=None, help='dataset directory')
    parser.add_argument('--all-dir', type=str, default=None, help='dataset directory')

    args = parser.parse_args()
    eval(args)

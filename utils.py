#!/usr/bin/python
# -*- encoding: utf-8 -*-

import torch
import numpy as np
from PIL import Image
from autoencoders import AE, VAE
from backbones import ResNetEncoder, VGGEncoder, DenseNetEncoder, SwinEncoder
from classifier import Classifier

def load_model(backbone_type, backbone_dir, classifier_dir, ae_dir, ae_type):
    # load backbone
    if backbone_type == 'resnet':
        output_size = (256, 128)
        backbone = ResNetEncoder()
    elif backbone_type == 'vgg':
        output_size = (256, 128)
        backbone = VGGEncoder()
    elif backbone_type == 'dense':
        output_size = (256, 128)
        backbone = DenseNetEncoder()
    elif backbone_type == 'swin':
        output_size = (224, 224)
        backbone  = SwinEncoder()
    else:
        print('No valid backbone model specified')
        exit(1)
    backbone.load_state_dict(torch.load(backbone_dir))
    backbone = backbone.cuda()

    # load autoencoder
    if ae_type == 'vae':
        ae = VAE(input_size=backbone.output_size, orig_height=output_size[0], orig_width=output_size[1]).cuda()
    elif ae_type in ['ae', 'sae', 'dae']:
        ae = AE(input_size=backbone.output_size, orig_height=output_size[0], orig_width=output_size[1]).cuda()
    else:
        print('Invalid autoencoder type')
        exit()
    ae.load_state_dict(torch.load(ae_dir))
    ae = ae.cuda()

    # load classifier
    classifier = Classifier(input_size=1456).cuda()
    classifier.load_state_dict(torch.load(classifier_dir))

    return backbone, ae, classifier


def pdist_torch(emb1, emb2):
    '''
    compute the eucilidean distance matrix between embeddings1 and embeddings2
    using gpu
    '''
    m, n = emb1.shape[0], emb2.shape[0]
    emb1_pow = torch.pow(emb1, 2).sum(dim = 1, keepdim = True).expand(m, n)
    emb2_pow = torch.pow(emb2, 2).sum(dim = 1, keepdim = True).expand(n, m).t()
    dist_mtx = emb1_pow + emb2_pow
    dist_mtx = dist_mtx.addmm_(1, -2, emb1, emb2.t())
    dist_mtx = dist_mtx.clamp(min = 1e-12).sqrt()
    return dist_mtx


def pdist_np(emb1, emb2):
    '''
    compute the eucilidean distance matrix between embeddings1 and embeddings2
    using cpu
    '''
    m, n = emb1.shape[0], emb2.shape[0]
    emb1_pow = np.square(emb1).sum(axis = 1)[..., np.newaxis]
    emb2_pow = np.square(emb2).sum(axis = 1)[np.newaxis, ...]
    dist_mtx = -2 * np.matmul(emb1, emb2.T) + emb1_pow + emb2_pow
    dist_mtx = np.sqrt(dist_mtx.clip(min = 1e-12))
    return dist_mtx


if __name__ == "__main__":
    a = np.arange(4*128).reshape(4, 128)
    b = np.arange(10, 10 + 5*128).reshape(5, 128)
    r1 = pdist_np(a, b)
    print(r1.shape)
    print(r1)

    a = torch.Tensor(a)
    b = torch.Tensor(b)
    r2 = pdist_torch(a, b)
    print(r2.shape)
    print(r2)

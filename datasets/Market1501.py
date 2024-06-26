#!/usr/bin/python
# -*- encoding: utf-8 -*-


import os
import torch
import torchvision
import torchvision.transforms as transforms
from torch.utils.data import Dataset
import cv2
import numpy as np
from PIL import Image

from random_erasing import RandomErasing

class Market1501(Dataset):
    '''
    a wrapper of Market1501 dataset
    '''
    def __init__(self, data_path, is_train=True, use_swin=False, *args, **kwargs):
        super(Market1501, self).__init__(*args, **kwargs)
        self.is_train = is_train
        self.data_path = data_path
        self.imgs = [el for el in os.listdir(data_path) if os.path.splitext(el)[1] == '.jpg']
        self.lb_ids = [int(el.split('_')[0]) for el in self.imgs]
        self.lb_cams = [int(el.split('_')[1][1]) for el in self.imgs]
        self.imgs = [os.path.join(data_path, el) for el in self.imgs]
        if is_train:
            if use_swin:
                self.trans = transforms.Compose([
                transforms.Resize((224, 112)),  # Resize height to 224 and maintain aspect ratio
                transforms.Pad((56, 0, 56, 0), fill=0),
                transforms.RandomHorizontalFlip(),
                transforms.ToTensor(),
                transforms.Normalize((0.486, 0.459, 0.408), (0.229, 0.224, 0.225)),
                ])
            else:
                self.trans = transforms.Compose([
                    transforms.Resize((256, 128)),
                    transforms.RandomHorizontalFlip(),
                    transforms.ToTensor(),
                    transforms.Normalize((0.486, 0.459, 0.408), (0.229, 0.224, 0.225)),
                ])
        else:
            if use_swin:
                self.trans = transforms.Compose([
                transforms.Resize((224, 112)),
                transforms.Pad((56, 0, 56, 0), fill=0),
                transforms.ToTensor(),
                transforms.Normalize((0.486, 0.459, 0.408), (0.229, 0.224, 0.225))])
            else:
                self.trans = transforms.Compose([
                    transforms.Resize((256, 128)),
                    transforms.ToTensor(),
                    transforms.Normalize((0.486, 0.459, 0.408), (0.229, 0.224, 0.225)),
                ])

        # useful for sampler
        self.lb_img_dict = dict()
        self.lb_ids_uniq = set(self.lb_ids)
        lb_array = np.array(self.lb_ids)
        for lb in self.lb_ids_uniq:
            idx = np.where(lb_array == lb)[0]
            self.lb_img_dict.update({lb: idx})

    def __len__(self):
        return len(self.imgs)

    def __getitem__(self, idx):
        img = Image.open(self.imgs[idx])
        img = self.trans(img)
        return img, self.lb_ids[idx], self.lb_cams[idx]


if __name__ == "__main__":
    ds = Market1501('./Market-1501-v15.09.15/bounding_box_train', is_train = True)
    im, _, _ = ds[1]
    print(im.shape)
    print(im.max())
    print(im.min())
    ran_er = RandomErasing()
    im = ran_er(im)
    cv2.imshow('erased', im)
    cv2.waitKey(0)

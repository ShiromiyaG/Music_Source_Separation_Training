# coding: utf-8
__author__ = 'Roman Solovyev (ZFTurbo): https://github.com/ZFTurbo/'

import argparse
import time
import librosa
from tqdm import tqdm
import sys
import os
import glob
import torch
import numpy as np
import soundfile as sf
import torch.nn as nn
from utils import demix_track, demix_track_demucs, get_model_from_config

import warnings
warnings.filterwarnings("ignore")


def run_file(model, args, config, device, verbose=False):
    start_time = time.time()
    model.eval()

    instruments = config.training.instruments
    if config.training.target_instrument is not None:
        instruments = [config.training.target_instrument]

    if not os.path.isdir(args.store_dir):
        os.mkdir(args.store_dir)

    path = args.input_file
    try:
        mix, sr = librosa.load(path, sr=44100, mono=False)
        mix = mix.T
    except Exception as e:
        print('Can read track: {}'.format(path))
        print('Error message: {}'.format(str(e)))
        return

    # Convert mono to stereo if needed
    if len(mix.shape) == 1:
        mix = np.stack([mix, mix], axis=-1)

    mixture = torch.tensor(mix.T, dtype=torch.float32)
    if args.model_type == 'htdemucs':
        res = demix_track_demucs(config, model, mixture, device)
    else:
        res = demix_track(config, model, mixture, device)
    for instr in instruments:
        sf.write("{}/{}_{}.wav".format(args.store_dir, os.path.basename(path)[:-4], instr), res[instr].T, sr, subtype='FLOAT')

    time.sleep(1)
    print("Elapsed time: {:.2f} sec".format(time.time() - start_time))


def proc_file(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_type", type=str, default='mdx23c', help="One of mdx23c, htdemucs, segm_models, mel_band_roformer, bs_roformer, swin_upernet, bandit")
    parser.add_argument("--config_path", type=str, help="path to config file")
    parser.add_argument("--start_check_point", type=str, default='', help="Initial checkpoint to valid weights")
    parser.add_argument("--input_file", type=str, help="file to process")
    parser.add_argument("--store_dir", default="", type=str, help="path to store results as wav file")
    parser.add_argument("--device_ids", nargs='+', type=int, default=0, help='list of gpu ids')
    if args is None:
        args = parser.parse_args()
    else:
        args = parser.parse_args(args)

    torch.backends.cudnn.benchmark = True

    model, config = get_model_from_config(args.model_type, args.config_path)
    if args.start_check_point != '':
        print('Start from checkpoint: {}'.format(args.start_check_point))
        state_dict = torch.load(args.start_check_point)
        if args.model_type == 'htdemucs':
            # Fix for htdemucs pround etrained models
            if 'state' in state_dict:
                state_dict = state_dict['state']
        model.load_state_dict(state_dict)
    print("Instruments: {}".format(config.training.instruments))

    if torch.cuda.is_available():
        device_ids = args.device_ids
        if type(device_ids)==int:
            device = torch.device(f'cuda:{device_ids}')
            model = model.to(device)
        else:
            device = torch.device(f'cuda:{device_ids[0]}')
            model = nn.DataParallel(model, device_ids=device_ids).to(device)
    else:
        device = 'cpu'
        print('CUDA is not avilable. Run inference on CPU. It will be very slow...')
        model = model.to(device)

    run_file(model, args, config, device, verbose=False)

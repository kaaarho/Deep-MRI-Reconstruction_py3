#!/usr/bin/env python

import time

import theano
import theano.tensor as T

import lasagne
import argparse

from os.path import join

from utils import compressed_sensing as cs
from utils.metric import complex_psnr

from cascadenet.network.model import build_d5_c5
from cascadenet.util.helpers import from_lasagne_format
from cascadenet.util.helpers import to_lasagne_format

from dataloader.data_loader_RBHTDTCMR2024A_d40 import *
from mask_loader import *

from tqdm import tqdm


def prep_input(im, mask):
    """Undersample the batch, then reformat them into what the network accepts.

    Parameters
    ----------
    gauss_ivar: float - controls the undersampling rate.
                        higher the value, more undersampling
    """

    im_und, k_und = cs.undersample_kspace(im, mask)
    im_gnd_l = to_lasagne_format(im)
    im_und_l = to_lasagne_format(im_und)
    k_und_l = to_lasagne_format(k_und)
    mask_l = to_lasagne_format(mask, mask=True)

    return im_und_l, k_und_l, mask_l, im_gnd_l


def iterate_minibatch(data, batch_size, shuffle=True, drop_last=False):
    n = len(data)

    if shuffle:
        data = np.random.permutation(data)

    if drop_last:
        n = n - n % batch_size

    for i in range(0, n, batch_size):
        yield data[i:i+batch_size]


def create_dummy_data(data_path, log_folder_path, h, w, phase='train', disease='', cphase='', debug=False):

    data, data_info = load_images(data_path, log_folder_path, h, w, phase, disease, cphase, debug=debug)

    return data, data_info


def compile_fn(network, net_config, args):
    """
    Create Training function and validation function
    """
    # Hyper-parameters
    base_lr = float(args.lr)
    l2 = float(args.l2)

    # Theano variables
    input_var = net_config['input'].input_var
    mask_var = net_config['mask'].input_var
    kspace_var = net_config['kspace_input'].input_var
    target_var = T.tensor4('targets')

    # Objective
    pred = lasagne.layers.get_output(network)
    # complex valued signal has 2 channels, which counts as 1.
    loss_sq = lasagne.objectives.squared_error(target_var, pred).mean() * 2
    if l2:
        l2_penalty = lasagne.regularization.regularize_network_params(network, lasagne.regularization.l2)
        loss = loss_sq + l2_penalty * l2

    update_rule = lasagne.updates.adam
    params = lasagne.layers.get_all_params(network, trainable=True)
    updates = update_rule(loss, params, learning_rate=base_lr)

    print(' Compiling ... ')
    t_start = time.time()
    train_fn = theano.function([input_var, mask_var, kspace_var, target_var],
                               [loss], updates=updates,
                               on_unused_input='ignore')

    val_fn = theano.function([input_var, mask_var, kspace_var, target_var],
                             [loss, pred],
                             on_unused_input='ignore')
    t_end = time.time()
    print(' ... Done, took %.4f s' % (t_end - t_start))

    return train_fn, val_fn


def mkdir(path):
    if not os.path.exists(path):
        os.makedirs(path)

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--task_name', type=str,)
    parser.add_argument('--data_path', type=str, default="/media/NAS_CMR/DTCMR/Newpipeline/Data_pickle4/Data/",)
    parser.add_argument('--log_folder_path', type=str, default="/media/NAS06/jiahao/RBHT_DTCMR_2024A/d.3.0.debug/log",)
    parser.add_argument('--disease', type=str, default='AllDisease', help='AllDisease or HEALTHY')
    parser.add_argument('--cphase', default=["systole", "diastole"], help='diastole or systole')
    parser.add_argument('--num_epoch', type=int, default=10, help='number of epochs')
    parser.add_argument('--batch_size', type=int, default=10, help='batch size')
    parser.add_argument('--lr', type=float, default=0.001, help='initial learning rate')
    parser.add_argument('--l2', type=float, default=1e-6, help='l2 regularisation')
    parser.add_argument('--undersampling_mask', type=str, default="fMRI_Reg_AF4_CF0.08_PE48", help='Undersampling mask for k-space sampling')
    parser.add_argument('--resolution_h', type=int, default=256, help='Undersampling mask for k-space sampling')
    parser.add_argument('--resolution_w', type=int, default=96, help='Undersampling mask for k-space sampling')
    parser.add_argument('--debug', action='store_true', help='debug mode')
    parser.add_argument('--savefig', action='store_true', help='Save output images and masks')

    args = parser.parse_args()

    print(theano.config.device)

    # Project config
    undersampling_mask = args.undersampling_mask
    num_epoch = args.num_epoch
    batch_size = args.batch_size
    Nx, Ny = args.resolution_h, args.resolution_w
    save_fig = args.savefig
    save_every = 1
    data_path = args.data_path
    log_folder_path = args.log_folder_path
    disease = args.disease
    cphase = args.cphase
    debug = args.debug
    model_name = 'DCCNN_D5C5_RBHTDTCMR2024A_{}_{}_{}'.format(undersampling_mask, disease, 'all')

    # Configure directory info
    project_root = '/home/jh/Deep-MRI-Reconstruction_py3'
    save_dir = join(project_root, 'models/%s' % model_name)
    if not os.path.isdir(save_dir):
        os.makedirs(save_dir)

    # Specify network
    input_shape = (batch_size, 2, Nx, Ny)
    net_config, net,  = build_d5_c5(input_shape)

    # D5-C5 with pre-trained parameters
    # with np.load('./models/pretrained/d5_c5.npz') as f:
    #     param_values = [f['arr_{0}'.format(i)] for i in range(len(f.files))]
    #     lasagne.layers.set_all_param_values(net, param_values)

    # Compile function
    train_fn, val_fn = compile_fn(net, net_config, args)

    # Create dataset
    train, train_info = create_dummy_data(data_path, log_folder_path, Nx, Ny, phase='train', disease=disease, cphase=cphase, debug=debug)
    # validate, val_info = create_dummy_data(data_path, log_folder_path, Nx, Ny, phase='val', disease=disease, cphase=cphase, debug=debug)
    test, test_info = create_dummy_data(data_path, log_folder_path, Nx, Ny, phase='test', disease=disease, cphase=cphase, debug=debug)

    print('Start Training...')
    for epoch in range(num_epoch):
        t_start = time.time()

        # Training
        print('Training')
        train_err = 0
        train_batches = 0
        # Load mask
        mask_1d = load_mask(undersampling_mask)
        mask_1d = mask_1d[:, np.newaxis]
        mask = np.repeat(mask_1d, 128, axis=1).transpose((1, 0))
        mask = np.pad(mask, ((64, 64), (24, 24)), mode='constant')
        mask = scipy.fftpack.ifftshift(mask)
        mask_bs = mask[np.newaxis, :, :]
        mask_complex = np.repeat(mask_bs, batch_size, axis=0).astype(float)
        cv2.imwrite('./tmp/mask_check.png', mask * 255)

        for im in tqdm(iterate_minibatch(train, batch_size, shuffle=True, drop_last=True)):

            # im (BS, 256, 96) float
            # mask_complex (BS, 256, 96) float

            # im_und (BS, 1, 256, 96) float ?
            # k_und (BS, 1, 256, 96) float ?
            # mask (BS, 1, 256, 96) float ?
            # im_gnd (BS, 1, 256, 96) float ?
            im_und, k_und, mask, im_gnd = prep_input(im, mask_complex)
            err = train_fn(im_und, mask, k_und, im_gnd)[0]
            train_err += err
            train_batches += 1

        train_err /= train_batches
        t_end = time.time()

        # Testing
        print('Testing')
        vis = []
        test_err = 0
        base_psnr = 0
        test_psnr = 0
        test_batches = 0
        i = 0

        # Load mask
        mask_complex = np.repeat(mask_bs, 1, axis=0).astype(float)
        cv2.imwrite('./tmp/mask_check.png', mask * 255)

        if (epoch + 1) % 1 == 0:
            for im in tqdm(iterate_minibatch(test, 1, shuffle=False, drop_last=False)):

                # im (BS, 256, 96)
                # mask (BS, 256, 96)
                im_und, k_und, mask, im_gnd = prep_input(im, mask_complex)

                err, pred = val_fn(im_und, mask, k_und, im_gnd)

                test_err += err
                for im_i, und_i, pred_i in zip(im, from_lasagne_format(im_und), from_lasagne_format(pred)):
                    base_psnr += complex_psnr(im_i, und_i, peak='max')
                    test_psnr += complex_psnr(im_i, pred_i, peak='max')

                    gt = abs(im)[0]
                    recon = abs(from_lasagne_format(pred))[0]
                    zf = abs(from_lasagne_format(im_und))[0]

                    # crop
                    gt = gt[80:176, :]
                    recon = recon[80:176, :]
                    zf = zf[80:176, :]

                    if save_fig and i < 10:
                        mkdir(os.path.join(save_dir, 'epoch_{}'.format(epoch + 1), 'png', 'GT'))
                        cv2.imwrite(os.path.join(save_dir, 'epoch_{}'.format(epoch + 1), 'png', 'GT', 'GT_{:04d}.png'.format(i)), gt*255)
                        mkdir(os.path.join(save_dir, 'epoch_{}'.format(epoch + 1), 'png', 'Recon'))
                        cv2.imwrite(os.path.join(save_dir, 'epoch_{}'.format(epoch + 1), 'png', 'Recon', 'Recon_{:04d}.png'.format(i)), recon*255)
                        mkdir(os.path.join(save_dir, 'epoch_{}'.format(epoch + 1), 'png', 'ZF'))
                        cv2.imwrite(os.path.join(save_dir, 'epoch_{}'.format(epoch + 1), 'png', 'ZF', 'ZF_{:04d}.png'.format(i)), zf*255)

                    test_batches += 1
                    i = i + 1

            test_err /= test_batches
            base_psnr /= (test_batches * batch_size)
            test_psnr /= (test_batches * batch_size)

        print("Epoch {}/{}".format(epoch + 1, num_epoch))
        print(" time: {}s".format(t_end - t_start))
        print(" training loss:\t\t{:.6f}".format(train_err))
        if (epoch + 1) % 20 == 0:
            print(" test loss:\t\t{:.6f}".format(test_err))
            print(" base PSNR:\t\t{:.6f}".format(base_psnr))
            print(" test PSNR:\t\t{:.6f}".format(test_psnr))

        # save the model
        if (epoch + 1) % 10 == 0:
            name = '%s_epoch_%d.npz' % (model_name, epoch + 1)
            np.savez(join(save_dir, name), *lasagne.layers.get_all_param_values(net))
            print('model parameters saved at %s' % join(os.getcwd(), name))


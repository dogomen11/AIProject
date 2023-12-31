import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import os
import sys
import librosa
import librosa.display as display
import soundfile as sf
import os
import torch
import cv2

import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader, random_split

import torchvision
import torchvision.transforms as transforms
import torchvision.datasets as datasets

from pathlib import Path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from utils import *

################ Late Reverberation Supression U-net ################

class LateSupUnet(nn.Module):
	"""
	Late Reverberation Supression U-net
	"""
	def __init__(self, n_channels=1, bilinear=True):
		super(LateSupUnet, self).__init__()
		self.n_channels = n_channels
		self.bilinear = bilinear
		self.inc = DoubleConv(n_channels, 64)
		self.down1 = Down(64, 128)
		self.down2 = Down(128, 256)
		self.down3 = Down(256, 512)
		factor = 2 if bilinear else 1
		self.down4 = Down(512, 1024 // factor)
		self.up1 = Up(1024, 512 // factor, bilinear)
		self.up2 = Up(512, 256 // factor, bilinear)
		self.up3 = Up(256, 128 // factor, bilinear)
		self.up4 = Up(128, 64, bilinear)
		self.outc = OutConv(64, 1)

	def forward(self, input):
		x1 = self.inc(input)
		x2 = self.down1(x1)
		x3 = self.down2(x2)
		x4 = self.down3(x3)
		x5 = self.down4(x4)
		x = self.up1(x5, x4)
		x = self.up2(x, x3)
		x = self.up3(x, x2)
		x = self.up4(x, x1)
		x = self.outc(x)
		output = input - x
		return output


###################################################################################################################
###################################################################################################################
#                          
#                          ░██████╗████████╗░█████╗░██████╗░████████╗
#                          ██╔════╝╚══██╔══╝██╔══██╗██╔══██╗╚══██╔══╝
#                          ╚█████╗░░░░██║░░░███████║██████╔╝░░░██║░░░
#                          ░╚═══██╗░░░██║░░░██╔══██║██╔══██╗░░░██║░░░
#                          ██████╔╝░░░██║░░░██║░░██║██║░░██║░░░██║░░░
#                          ╚═════╝░░░░╚═╝░░░╚═╝░░╚═╝╚═╝░░╚═╝░░░╚═╝░░░
#                          
###################################################################################################################
###################################################################################################################
### ------------------------ TRAIN ------------------------ 

def load_data():
  X_train1 = torch.load('/home/may.tiger/AIProject/data/data_audio/non_norm_data/X_train_1.pth')
  X_train2 = torch.load('/home/may.tiger/AIProject/data/data_audio/non_norm_data/X_train_2.pth')
  X_train3 = torch.load('/home/may.tiger/AIProject/data/data_audio/non_norm_data/X_train_3.pth')
  X_train4 = torch.load('/home/may.tiger/AIProject/data/data_audio/non_norm_data/X_train_4.pth')
  y_train1 = torch.load('/home/may.tiger/AIProject/data/data_audio/non_norm_data/y_train_1.pth')
  y_train2 = torch.load('/home/may.tiger/AIProject/data/data_audio/non_norm_data/y_train_2.pth')
  y_train3 = torch.load('/home/may.tiger/AIProject/data/data_audio/non_norm_data/y_train_3.pth')
  y_train4 = torch.load('/home/may.tiger/AIProject/data/data_audio/non_norm_data/y_train_4.pth')
  
  X = torch.cat((X_train1, X_train2, X_train3, X_train4))
  y = torch.cat((y_train1, y_train2, y_train3, y_train4))
  total_dataset = ReverbDataset(X, y)
  length_train = int(len(total_dataset)*0.85)
  length_val = len(total_dataset) - length_train
  lengths = [length_train, length_val]
  dataset_train, dataset_val = random_split(total_dataset, lengths)
  print(len(dataset_train))
  print(len(dataset_val))
  
  return dataset_train, dataset_val

def trainer(model, train_loader, val_loader, checkpoints, nEpochs = 30, lr = 1e-3):
  """
  Train model

  model: U-net model on GPU
  train_loader: dataloader containing train examples
  val_loader: dataloader containing validation examples
  checkpoints: list of directories to save the model, train loss and Val loss respectively
  """
  criterion = nn.MSELoss()
  beta1 = 0.5
  beta2 = 0.999
  lr_decay = 0.97
  decay_rate = 2
  optimizer = torch.optim.Adam(model.parameters(), lr, (beta1, beta2))

  train_loss = []
  val_loss = []
  
  model.train()
  for epoch in range(nEpochs):
    temp_train_loss = 0.0
    corrects_train = 0
    for i, (rev_data, clean_data) in enumerate(train_loader):
      rev_data = rev_data.cuda()
      clean_data = clean_data.cuda()

      optimizer.zero_grad()
      output = model(rev_data)
      loss_train = criterion(output, clean_data)
      loss_train.backward()
      optimizer.step()

      temp_train_loss += loss_train.item()/len(train_loader)

    temp_val_loss = 0.0    
    #Validacion
    model.eval()
    with torch.no_grad():
      for i, (rev_data, clean_data) in enumerate(val_loader):
        rev_data = rev_data.cuda()
        clean_data = clean_data.cuda()
        output = model(rev_data)
        loss_val = criterion(output, clean_data)
        temp_val_loss += loss_val.item()/len(val_loader)

    train_loss.append(temp_train_loss)
    val_loss.append(temp_val_loss)

    print('Epoch : {} || Train Loss: {:.3f} || Val Loss: {:.3f}'\
         .format(epoch+1, loss_train.item(), loss_val.item()))
    model.train()
    
    if ((epoch+1)%5 == 0):
      torch.save(model.state_dict(), checkpoints[0])
      torch.save(train_loss, checkpoints[1])
      torch.save(val_loss, checkpoints[2])
      print("saved models")

    if (epoch % decay_rate == 1):
       optimizer.param_groups[0]['lr'] *= lr_decay

  return train_loss, val_loss

def LSUnet_train():
  dataset_train, dataset_val = load_data()
  train_loader = DataLoader(dataset_train, batch_size = 16, shuffle = True, num_workers = 4, pin_memory = True)
  val_loader = DataLoader(dataset_val, batch_size = 16, shuffle = True, num_workers = 4, pin_memory = True)
  net = LateSupUnet(n_channels=1, bilinear=False).cuda()
  checkpoints = ['/home/may.tiger/AIProject/data/training/model/LateSupUnet_state_dict.pth', 
                 '/home/may.tiger/AIProject/data/training/losses/train_loss_LateSupUnet.pth', 
                 '/home/may.tiger/AIProject/data/training/losses/val_loss_LateSupUnet.pth']
  
  epochs = 25
  lr = 2e-4
  train_loss, val_loss = trainer(net, train_loader, val_loader, checkpoints, lr=lr, epochs = 25)

  train_loss = torch.load('/home/may.tiger/AIProject/data/training/losses/train_loss_LateSupUnet.pth')
  val_loss   = torch.load('/home/may.tiger/AIProject/data/training/losses/val_loss_LateSupUnet.pth')
  plt.style.reload_library()
  matplotlib.rc('xtick', labelsize=10) 
  matplotlib.rc('ytick', labelsize=10)
  matplotlib.rcParams.update({'font.size': 10})
  plt.figure()
  plt.rcParams["font.family"] = "serif"
  plt.plot(np.arange(1, (epochs+1), 1), train_loss, '-', label = 'Train loss')
  plt.plot(np.arange(1, (epochs+1), 1), val_loss, '-', label = 'Validation loss')
  plt.xlabel('Epochs')
  plt.ylabel('MSE loss')
  plt.grid()
  plt.legend()
  plt.savefig(f"LS_Unet_MSE_loss_to_epochs.jpg")

### ------------------------ EVALUATION ------------------------ 

def evaluate_by_audio(model_G, counter, audio_dirs, num_example, speech_rate=16000):
  """
  net: Unet model on CPU
  audio_dirs: list of directories containing reverberant spectrograms, clean spectrograms,
              reverberant waveforms and clean waveforms respectively
  num_example: example number in data
  speech_rate: sampling rate of speech data  
  """
  model_G.eval()
  matplotlib.rc('xtick', labelsize=15) 
  matplotlib.rc('ytick', labelsize=15)
  matplotlib.rcParams.update({'font.size': 15})
  plt.rcParams["font.family"] = "serif"

  X_test = torch.load(audio_dirs[0])
  y_test = torch.load(audio_dirs[1])
  waves = torch.load(audio_dirs[2])
  waves_target = torch.load(audio_dirs[3])
  dataset_test = ReverbDataset(X_test, y_test)

  original_spec = generate_spec(waves[num_example], speech_rate)
  clean_spec = generate_spec(waves_target[num_example], speech_rate)
  
  original_size = original_spec.shape
  reverbed_example = dataset_test.__getitem__(num_example)[0]
  reverbed_example_aux = reverbed_example.numpy()
  reverbed_example = torch.tensor(reverbed_example_aux[None, :, :, :], dtype=torch.float32)
  dereverbed_spec = model_G(reverbed_example)
  dereverbed_spec = dereverbed_spec.clone().detach().cpu().numpy()
  dereverbed_spec = dereverbed_spec[0, 0, :, :]
  dereverbed_spec = cv2.resize(dereverbed_spec, dsize = (original_size[1], original_size[0]), interpolation = cv2.INTER_LANCZOS4)

  graph_spec(original_spec,     save_path=("LSUnet_reverbed"+counter))
  graph_spec(clean_spec,        save_path=("LSUnet_original"+counter))
  graph_spec(dereverbed_spec,   save_path=("LSUnet_de_reverbed"+counter))
  
def LSUnet_extract_examples():
  """
  extracts 3 random examples from the test set and saves them in the data folder as .wav files and .png spectrograms
  """
  model_unet = LateSupUnet(n_channels=1, bilinear=False)
  model_unet.load_state_dict(torch.load('/home/may.tiger/AIProject/data/training/model/LateSupUnet_state_dict.pth', map_location=lambda storage, loc: storage))
  dir_list = ['/home/may.tiger/AIProject/data/data_audio/non_norm_data/X_test.pth', 
              '/home/may.tiger/AIProject/data/data_audio/non_norm_data/y_test.pth',
              '/home/may.tiger/AIProject/data/data_audio/non_norm_data/waverev.pth', 
              '/home/may.tiger/AIProject/data/data_audio/non_norm_data/wavetarget.pth']
  
  rand1, rand2, rand3 = np.random.randint(0, 500), np.random.randint(0, 500), np.random.randint(0, 500)
  counter = 0
  evaluate_by_audio(model_unet, counter, dir_list, rand1)
  counter = counter + 3
  evaluate_by_audio(model_unet, counter, dir_list, rand2)
  counter = counter + 3
  evaluate_by_audio(model_unet, counter, dir_list, rand3)

def evaluate(net, dataset, path, path_waves, init_example, end_example, speech_rate = 16000, initial = True, normalize_data = False):
  """
  net: U-net model used 
  dataset: reverb_dataset object to extract examples
  path: base directory to save results
  path_waves: directory containing reverb waveforms (not recovered from spectrograms)
  init_example: first example in dataset to be considered
  end_example: last example in dataset to be considered
  speech_rate: sampling rate of speech audios
  initial: True if is the first time executing, False if is not the first time
           if is False the new results are added to the existing results
  normalize_data: True if the net assumed normalized input 
  """

  device = torch.device("cuda:0" if(torch.cuda.is_available()) else "cpu")
  print('Current device: ' + str(device))

  if (initial):
    # reverb_pesq_list = []
    reverb_stoi_list = []
    reverb_llr_list = []
    reverb_cd_list = []
    reverb_fwSNRseg_list = []
    reverb_srmr_list = []

    # dereverb_pesq_list = []
    dereverb_stoi_list = []
    dereverb_llr_list = []
    dereverb_cd_list = []
    dereverb_fwSNRseg_list = []
    dereverb_srmr_list = []
  
  else:
    # reverb_pesq_list = torch.load(path + 'reverb_pesq_SupUnet.pth')
    reverb_stoi_list = torch.load(path + 'reverb_stoi_SupUnet.pth')
    reverb_llr_list = torch.load(path + 'reverb_llr_SupUnet.pth')
    reverb_cd_list = torch.load(path + 'reverb_cd_SupUnet.pth')
    reverb_fwSNRseg_list = torch.load(path + 'reverb_fwSNRseg_SupUnet.pth')
    reverb_srmr_list = torch.load(path + 'reverb_srmr_SupUnet.pth')

    # dereverb_pesq_list = torch.load(path + 'dereverb_pesq_SupUnet.pth')
    dereverb_stoi_list = torch.load(path + 'dereverb_stoi_SupUnet.pth')
    dereverb_llr_list = torch.load(path + 'dereverb_llr_SupUnet.pth')
    dereverb_cd_list = torch.load(path + 'dereverb_cd_SupUnet.pth')
    dereverb_fwSNRseg_list = torch.load(path + 'dereverb_fwSNRseg_SupUnet.pth')
    dereverb_srmr_list = torch.load(path + 'dereverb_srmr_SupUnet.pth')
  
  waves = torch.load(path_waves)
  net.eval()
  
  for i in range(init_example, end_example):
    print("Processing Example n°{}".format(i+1))
    real_spec = generate_spec(waves[i], speech_rate)
    rev_spec, clean_spec = dataset.__getitem__(i)
    clean_spec = clean_spec[0, :, :]
    net_input = torch.zeros((1, 1, rev_spec.shape[1], rev_spec.shape[2]))

    if normalize_data:
      norm_example, norm_stats_rev = linear_scaler(rev_spec[0, :, :].numpy())
      net_input[0, 0, :, :] = torch.tensor(norm_example)
      net_response = net(net_input.to(device))
      net_response = net_response.clone().detach().cpu().numpy() if torch.cuda.is_available() else net_response.clone().detach().numpy()
      net_response = (net_response-norm_stats_rev[1])/norm_stats_rev[0]


    else:
      net_input[0, :, :, :] = rev_spec
      net_response = net(net_input.to(device))
      net_response = net_response.clone().detach().cpu().numpy() if torch.cuda.is_available() else net_response.clone().detach().numpy()
  
    
    try:
      net_response = net_response[0, 0, :, :]
      recon_spec = cv2.resize(net_response, dsize = (real_spec.shape[1], real_spec.shape[0]), interpolation = cv2.INTER_LANCZOS4)
      clean_spec = cv2.resize(clean_spec.numpy(), dsize = (real_spec.shape[1], real_spec.shape[0]), interpolation = cv2.INTER_LANCZOS4)
      rev_spec = cv2.resize(rev_spec[0, :, :].numpy(), dsize = (real_spec.shape[1], real_spec.shape[0]), interpolation = cv2.INTER_LANCZOS4)

      original = reconstruct_wave(clean_spec)
      reverb = reconstruct_wave(rev_spec)
      recon = reconstruct_wave(recon_spec)
      recon_srmr = recon

      # pesq_metric_rev = pesq(original[0:len(reverb)], reverb, fs = speech_rate)
      stoi_metric_rev = stoi(original[0:len(reverb)], reverb, speech_rate)
      llr_metric_rev = llr(original[0:len(reverb)], reverb, speech_rate)
      cd_metric_rev = cepstrum_distance(original[0:len(reverb)], reverb, speech_rate)
      fwSNRseg_metric_rev = fwSNRseg(original[0:len(reverb)], reverb, speech_rate)
      srmr_metric_rev = srmr(waves[i], speech_rate)

      # pesq_metric_recon = pesq(original[0:len(recon)], recon, fs = speech_rate)
      stoi_metric_recon = stoi(original[0:len(recon)], recon, speech_rate)
      llr_metric_recon = llr(original[0:len(recon)], recon, speech_rate)
      cd_metric_recon = cepstrum_distance(original[0:len(recon)], recon, speech_rate)
      fwSNRseg_metric_recon = fwSNRseg(original[0:len(recon)], recon, speech_rate)
      srmr_metric_recon = srmr(recon_srmr, speech_rate)

      # reverb_pesq_list.append(pesq_metric_rev)
      reverb_stoi_list.append(stoi_metric_rev)
      reverb_llr_list.append(llr_metric_rev)
      reverb_cd_list.append(cd_metric_rev)
      reverb_fwSNRseg_list.append(fwSNRseg_metric_rev)
      reverb_srmr_list.append(srmr_metric_rev)

      # dereverb_pesq_list.append(pesq_metric_recon)
      dereverb_stoi_list.append(stoi_metric_recon)
      dereverb_llr_list.append(llr_metric_recon)
      dereverb_cd_list.append(cd_metric_recon)
      dereverb_fwSNRseg_list.append(fwSNRseg_metric_recon)
      dereverb_srmr_list.append(srmr_metric_recon)

      # print('PESQ reverberated signal: {:.3f} || PESQ dereverberated signal: {:.3f}'.format(pesq_metric_rev, pesq_metric_recon))
      print('STOI reverberated signal: {:.3f} || STOI dereverberated signal: {:.3f}'.format(stoi_metric_rev, stoi_metric_recon))
      print('LLR reverberated signal: {:.3f} || LLR dereverberated signal: {:.3f}'.format(llr_metric_rev, llr_metric_recon))
      print('CD reverberated signal: {:.3f} || CD dereverberated signal: {:.3f}'.format(cd_metric_rev, cd_metric_recon))
      print('fwSNRseg reverberated signal: {:.3f} || fwSNRseg dereverberated signal: {:.3f}'.format(fwSNRseg_metric_rev, fwSNRseg_metric_recon))
      print('SRMR reverberated signal: {:.3f} || SRMR dereverberated signal: {:.3f}'.format(srmr_metric_rev, srmr_metric_recon))

    except librosa.feature.inverse.ParameterError: 
      pass

    if ((i+1)%5 == 0):
      # torch.save(reverb_pesq_list, path + 'reverb_pesq_SupUnet.pth')
      torch.save(reverb_stoi_list, path + 'reverb_stoi_SupUnet.pth')
      torch.save(reverb_llr_list, path + 'reverb_llr_SupUnet.pth')
      torch.save(reverb_cd_list, path + 'reverb_cd_SupUnet.pth')
      torch.save(reverb_fwSNRseg_list, path + 'reverb_fwSNRseg_SupUnet.pth')
      torch.save(reverb_srmr_list, path + 'reverb_srmr_SupUnet.pth')

      # torch.save(dereverb_pesq_list, path + 'dereverb_pesq_SupUnet.pth')
      torch.save(dereverb_stoi_list, path + 'dereverb_stoi_SupUnet.pth')
      torch.save(dereverb_llr_list, path + 'dereverb_llr_SupUnet.pth')
      torch.save(dereverb_cd_list, path + 'dereverb_cd_SupUnet.pth')
      torch.save(dereverb_fwSNRseg_list, path + 'dereverb_fwSNRseg_SupUnet.pth')
      torch.save(dereverb_srmr_list, path + 'dereverb_srmr_SupUnet.pth')
      
      print('Saved')

def LSUnet_eval():
  path = '/home/may.tiger/AIProject/data/metrics_audio/room1/'
  path_waves = '/home/may.tiger/AIProject/data/data_audio/non_norm_data/waverev.pth'
  X_test = torch.load('/home/may.tiger/AIProject/data/data_audio/non_norm_data/X_test.pth')
  y_test = torch.load('/home/may.tiger/AIProject/data/data_audio/non_norm_data/y_test.pth')
  model_unet = LateSupUnet(n_channels=1, bilinear=False)
  model_unet.load_state_dict(torch.load('/home/may.tiger/AIProject/data/training/model/LateSupUnet_state_dict.pth', map_location=lambda storage, loc: storage))
  model_unet = model_unet.cuda()
  dataset_test = ReverbDataset(X_test, y_test)
  evaluate(model_unet, dataset_test, path, path_waves, 0, 500, initial = True, normalize_data=False)

  path = '/home/may.tiger/AIProject/data/metrics_audio/room1/'
  # reverb_pesq_list = torch.load(path + 'reverb_pesq_SupUnet.pth')
  reverb_stoi_list = torch.load(path + 'reverb_stoi_SupUnet.pth')
  reverb_llr_list = torch.load(path + 'reverb_llr_SupUnet.pth')
  reverb_cd_list = torch.load(path + 'reverb_cd_SupUnet.pth')
  reverb_fwSNRseg_list = torch.load(path + 'reverb_fwSNRseg_SupUnet.pth')
  reverb_srmr_list = torch.load(path + 'reverb_srmr_SupUnet.pth')

  # dereverb_pesq_list = torch.load(path + 'dereverb_pesq_SupUnet.pth')
  dereverb_stoi_list = torch.load(path + 'dereverb_stoi_SupUnet.pth')
  dereverb_llr_list = torch.load(path + 'dereverb_llr_SupUnet.pth')
  dereverb_cd_list = torch.load(path + 'dereverb_cd_SupUnet.pth')
  dereverb_fwSNRseg_list = torch.load(path + 'dereverb_fwSNRseg_SupUnet.pth')
  dereverb_srmr_list = torch.load(path + 'dereverb_srmr_SupUnet.pth')


  print('Results: \n')
  print('Reverberant signal:')
  # print('PESQ: {:.2f}'.format(np.mean(reverb_pesq_list)))
  print('STOI: {:.2f}'.format(np.mean(reverb_stoi_list)))
  print('LLR: {:.2f}'.format(np.mean(reverb_llr_list)))
  print('CD: {:.2f}'.format(np.mean(reverb_cd_list)))
  print('fwSNRseg: {:.2f}'.format(np.mean(reverb_fwSNRseg_list)))
  print('SRMR: {:.2f}'.format(np.mean(reverb_srmr_list)))

  print('\nDereverberated signal:')
  # print('PESQ: {:.2f}'.format(np.mean(dereverb_pesq_list)))
  print('STOI: {:.2f}'.format(np.mean(dereverb_stoi_list)))
  print('LLR: {:.2f}'.format(np.mean(dereverb_llr_list)))
  print('CD: {:.2f}'.format(np.mean(dereverb_cd_list)))
  print('fwSNRseg: {:.2f}'.format(np.mean(dereverb_fwSNRseg_list)))
  print('SRMR: {:.2f}'.format(np.mean(dereverb_srmr_list)))

  path = '/home/may.tiger/AIProject/data/metrics_audio/room2/'
  path_waves = '/home/may.tiger/AIProject/data/data_audio/non_norm_data/waverev_2.pth'
  X_test = torch.load('/home/may.tiger/AIProject/data/data_audio/non_norm_data/X_test_2.pth')
  y_test = torch.load('/home/may.tiger/AIProject/data/data_audio/non_norm_data/y_test_2.pth')
  model_unet = LateSupUnet(n_channels=1, bilinear=False)
  model_unet.load_state_dict(torch.load('/home/may.tiger/AIProject/data/training/model/LateSupUnet_state_dict.pth', map_location=lambda storage, loc: storage))
  model_unet = model_unet.cuda()
  dataset_test = ReverbDataset(X_test, y_test)
  evaluate(model_unet, dataset_test, path, path_waves, 0, 500, initial = True, normalize_data=False)

  path = '/home/may.tiger/AIProject/data/metrics_audio/room2/'
  # reverb_pesq_list = torch.load(path + 'reverb_pesq_SupUnet.pth')
  reverb_stoi_list = torch.load(path + 'reverb_stoi_SupUnet.pth')
  reverb_llr_list = torch.load(path + 'reverb_llr_SupUnet.pth')
  reverb_cd_list = torch.load(path + 'reverb_cd_SupUnet.pth')
  reverb_fwSNRseg_list = torch.load(path + 'reverb_fwSNRseg_SupUnet.pth')
  reverb_srmr_list = torch.load(path + 'reverb_srmr_SupUnet.pth')

  # dereverb_pesq_list = torch.load(path + 'dereverb_pesq_SupUnet.pth')
  dereverb_stoi_list = torch.load(path + 'dereverb_stoi_SupUnet.pth')
  dereverb_llr_list = torch.load(path + 'dereverb_llr_SupUnet.pth')
  dereverb_cd_list = torch.load(path + 'dereverb_cd_SupUnet.pth')
  dereverb_fwSNRseg_list = torch.load(path + 'dereverb_fwSNRseg_SupUnet.pth')
  dereverb_srmr_list = torch.load(path + 'dereverb_srmr_SupUnet.pth')


  print('Results: \n')
  print('Reverberant signal:')
  # print('PESQ: {:.2f}'.format(np.mean(reverb_pesq_list)))
  print('STOI: {:.2f}'.format(np.mean(reverb_stoi_list)))
  print('LLR: {:.2f}'.format(np.mean(reverb_llr_list)))
  print('CD: {:.2f}'.format(np.mean(reverb_cd_list)))
  print('fwSNRseg: {:.2f}'.format(np.mean(reverb_fwSNRseg_list)))
  print('SRMR: {:.2f}'.format(np.mean(reverb_srmr_list)))

  print('\nDereverberated signal:')
  # print('PESQ: {:.2f}'.format(np.mean(dereverb_pesq_list)))
  print('STOI: {:.2f}'.format(np.mean(dereverb_stoi_list)))
  print('LLR: {:.2f}'.format(np.mean(dereverb_llr_list)))
  print('CD: {:.2f}'.format(np.mean(dereverb_cd_list)))
  print('fwSNRseg: {:.2f}'.format(np.mean(dereverb_fwSNRseg_list)))
  print('SRMR: {:.2f}'.format(np.mean(dereverb_srmr_list)))

  path = '/home/may.tiger/AIProject/data/metrics_audio/room3/'
  path_waves = '/home/may.tiger/AIProject/data/data_audio/non_norm_data/waverev_3.pth'
  X_test = torch.load('/home/may.tiger/AIProject/data/data_audio/non_norm_data/X_test_3.pth')
  y_test = torch.load('/home/may.tiger/AIProject/data/data_audio/non_norm_data/y_test_3.pth')
  model_unet = LateSupUnet(n_channels=1, bilinear=False)
  model_unet.load_state_dict(torch.load('/home/may.tiger/AIProject/data/training/model/LateSupUnet_state_dict.pth', map_location=lambda storage, loc: storage))
  model_unet = model_unet.cuda()
  dataset_test = ReverbDataset(X_test, y_test)
  evaluate(model_unet, dataset_test, path, path_waves, 0, 500, initial = True, normalize_data=False)

  path = '/home/may.tiger/AIProject/data/metrics_audio/room3/'
  # reverb_pesq_list = torch.load(path + 'reverb_pesq_SupUnet.pth')
  reverb_stoi_list = torch.load(path + 'reverb_stoi_SupUnet.pth')
  reverb_llr_list = torch.load(path + 'reverb_llr_SupUnet.pth')
  reverb_cd_list = torch.load(path + 'reverb_cd_SupUnet.pth')
  reverb_fwSNRseg_list = torch.load(path + 'reverb_fwSNRseg_SupUnet.pth')
  reverb_srmr_list = torch.load(path + 'reverb_srmr_SupUnet.pth')

  # dereverb_pesq_list = torch.load(path + 'dereverb_pesq_SupUnet.pth')
  dereverb_stoi_list = torch.load(path + 'dereverb_stoi_SupUnet.pth')
  dereverb_llr_list = torch.load(path + 'dereverb_llr_SupUnet.pth')
  dereverb_cd_list = torch.load(path + 'dereverb_cd_SupUnet.pth')
  dereverb_fwSNRseg_list = torch.load(path + 'dereverb_fwSNRseg_SupUnet.pth')
  dereverb_srmr_list = torch.load(path + 'dereverb_srmr_SupUnet.pth')


  print('Results: \n')
  print('Reverberant signal:')
  # print('PESQ: {:.2f}'.format(np.mean(reverb_pesq_list)))
  print('STOI: {:.2f}'.format(np.mean(reverb_stoi_list)))
  print('LLR: {:.2f}'.format(np.mean(reverb_llr_list)))
  print('CD: {:.2f}'.format(np.mean(reverb_cd_list)))
  print('fwSNRseg: {:.2f}'.format(np.mean(reverb_fwSNRseg_list)))
  print('SRMR: {:.2f}'.format(np.mean(reverb_srmr_list)))

  print('\nDereverberated signal:')
  # print('PESQ: {:.2f}'.format(np.mean(dereverb_pesq_list)))
  print('STOI: {:.2f}'.format(np.mean(dereverb_stoi_list)))
  print('LLR: {:.2f}'.format(np.mean(dereverb_llr_list)))
  print('CD: {:.2f}'.format(np.mean(dereverb_cd_list)))
  print('fwSNRseg: {:.2f}'.format(np.mean(dereverb_fwSNRseg_list)))
  print('SRMR: {:.2f}'.format(np.mean(dereverb_srmr_list)))

  path = '/home/may.tiger/AIProject/data/metrics_audio/room4/'
  path_waves = '/home/may.tiger/AIProject/data/data_audio/non_norm_data/waverev_4.pth'
  X_test = torch.load('/home/may.tiger/AIProject/data/data_audio/non_norm_data/X_test_4.pth')
  y_test = torch.load('/home/may.tiger/AIProject/data/data_audio/non_norm_data/y_test_4.pth')
  model_unet = LateSupUnet(n_channels=1, bilinear=False)
  model_unet.load_state_dict(torch.load('/home/may.tiger/AIProject/data/training/model/LateSupUnet_state_dict.pth', map_location=lambda storage, loc: storage))
  model_unet = model_unet.cuda()
  dataset_test = ReverbDataset(X_test, y_test)
  evaluate(model_unet, dataset_test, path, path_waves, 0, 500, initial = True, normalize_data=False)

  path = '/home/may.tiger/AIProject/data/metrics_audio/room4/'
  # reverb_pesq_list = torch.load(path + 'reverb_pesq_SupUnet.pth')
  reverb_stoi_list = torch.load(path + 'reverb_stoi_SupUnet.pth')
  reverb_llr_list = torch.load(path + 'reverb_llr_SupUnet.pth')
  reverb_cd_list = torch.load(path + 'reverb_cd_SupUnet.pth')
  reverb_fwSNRseg_list = torch.load(path + 'reverb_fwSNRseg_SupUnet.pth')
  reverb_srmr_list = torch.load(path + 'reverb_srmr_SupUnet.pth')

  # dereverb_pesq_list = torch.load(path + 'dereverb_pesq_SupUnet.pth')
  dereverb_stoi_list = torch.load(path + 'dereverb_stoi_SupUnet.pth')
  dereverb_llr_list = torch.load(path + 'dereverb_llr_SupUnet.pth')
  dereverb_cd_list = torch.load(path + 'dereverb_cd_SupUnet.pth')
  dereverb_fwSNRseg_list = torch.load(path + 'dereverb_fwSNRseg_SupUnet.pth')
  dereverb_srmr_list = torch.load(path + 'dereverb_srmr_SupUnet.pth')


  print('Results: \n')
  print('Reverberant signal:')
  # print('PESQ: {:.2f}'.format(np.mean(reverb_pesq_list)))
  print('STOI: {:.2f}'.format(np.mean(reverb_stoi_list)))
  print('LLR: {:.2f}'.format(np.mean(reverb_llr_list)))
  print('CD: {:.2f}'.format(np.mean(reverb_cd_list)))
  print('fwSNRseg: {:.2f}'.format(np.mean(reverb_fwSNRseg_list)))
  print('SRMR: {:.2f}'.format(np.mean(reverb_srmr_list)))

  print('\nDereverberated signal:')
  # print('PESQ: {:.2f}'.format(np.mean(dereverb_pesq_list)))
  print('STOI: {:.2f}'.format(np.mean(dereverb_stoi_list)))
  print('LLR: {:.2f}'.format(np.mean(dereverb_llr_list)))
  print('CD: {:.2f}'.format(np.mean(dereverb_cd_list)))
  print('fwSNRseg: {:.2f}'.format(np.mean(dereverb_fwSNRseg_list)))
  print('SRMR: {:.2f}'.format(np.mean(dereverb_srmr_list)))

  path = '/home/may.tiger/AIProject/data/metrics_audio/room5/'
  path_waves = '/home/may.tiger/AIProject/data/data_audio/non_norm_data/waverev_5.pth'
  X_test = torch.load('/home/may.tiger/AIProject/data/data_audio/non_norm_data/X_test_5.pth')
  y_test = torch.load('/home/may.tiger/AIProject/data/data_audio/non_norm_data/y_test_5.pth')
  model_unet = LateSupUnet(n_channels=1, bilinear=False)
  model_unet.load_state_dict(torch.load('/home/may.tiger/AIProject/data/training/model/LateSupUnet_state_dict.pth', map_location=lambda storage, loc: storage))
  model_unet = model_unet.cuda()
  dataset_test = ReverbDataset(X_test, y_test)
  evaluate(model_unet, dataset_test, path, path_waves, 0, 500, initial = True, normalize_data=False)

  path = '/home/may.tiger/AIProject/data/metrics_audio/room5/'
  # reverb_pesq_list = torch.load(path + 'reverb_pesq_SupUnet.pth')
  reverb_stoi_list = torch.load(path + 'reverb_stoi_SupUnet.pth')
  reverb_llr_list = torch.load(path + 'reverb_llr_SupUnet.pth')
  reverb_cd_list = torch.load(path + 'reverb_cd_SupUnet.pth')
  reverb_fwSNRseg_list = torch.load(path + 'reverb_fwSNRseg_SupUnet.pth')
  reverb_srmr_list = torch.load(path + 'reverb_srmr_SupUnet.pth')

  # dereverb_pesq_list = torch.load(path + 'dereverb_pesq_SupUnet.pth')
  dereverb_stoi_list = torch.load(path + 'dereverb_stoi_SupUnet.pth')
  dereverb_llr_list = torch.load(path + 'dereverb_llr_SupUnet.pth')
  dereverb_cd_list = torch.load(path + 'dereverb_cd_SupUnet.pth')
  dereverb_fwSNRseg_list = torch.load(path + 'dereverb_fwSNRseg_SupUnet.pth')
  dereverb_srmr_list = torch.load(path + 'dereverb_srmr_SupUnet.pth')


  print('Results: \n')
  print('Reverberant signal:')
  # print('PESQ: {:.2f}'.format(np.mean(reverb_pesq_list)))
  print('STOI: {:.2f}'.format(np.mean(reverb_stoi_list)))
  print('LLR: {:.2f}'.format(np.mean(reverb_llr_list)))
  print('CD: {:.2f}'.format(np.mean(reverb_cd_list)))
  print('fwSNRseg: {:.2f}'.format(np.mean(reverb_fwSNRseg_list)))
  print('SRMR: {:.2f}'.format(np.mean(reverb_srmr_list)))

  print('\nDereverberated signal:')
  # print('PESQ: {:.2f}'.format(np.mean(dereverb_pesq_list)))
  print('STOI: {:.2f}'.format(np.mean(dereverb_stoi_list)))
  print('LLR: {:.2f}'.format(np.mean(dereverb_llr_list)))
  print('CD: {:.2f}'.format(np.mean(dereverb_cd_list)))
  print('fwSNRseg: {:.2f}'.format(np.mean(dereverb_fwSNRseg_list)))
  print('SRMR: {:.2f}'.format(np.mean(dereverb_srmr_list)))




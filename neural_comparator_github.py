# -*- coding: utf-8 -*-
"""
Created on Fri Jun 11 12:50:37 2021

This file is Python code based on Ludueña, G. A., & Gros, C. (2013). 
A self-organized neural comparator. Neural Computation, 25(4), 1006–1028. 
https://doi.org/10.1162/NECO_a_00424

This code is my own and was not written in collaboration with Ludueña and Gros.
Questions or comments regarding this file can be addressed to lieke.c@nin.knaw.nl

-------------------
The class defined in this file implements the neural comparator Matchnet;
Entry point for the model is the 'step()' function which defined what the matchnet
does during a single time step; this entails: 
1-  The construction of an input vector based on the trial type (match or non-match) 
2-  A feedforward pass that computes the match value x4
3-  A local anti-Hebbian learning rule that updates the weights of each neuron

The addition of the CIFAR-10 dataset is my own and it outside the scope of the paper.
I have extracted 10000 activity vectors of the second fully connected layer from the PyTorch
network that was improved by Caleb Woy. 
https://www.kaggle.com/whatsthevariance/pytorch-cnn-cifar10-68-70-test-accuracy
It is a first attempt to learn a neural comparator with real-life data.

@author: Lieke Ceton
"""
#%% Network architecture

import numpy as np
import matplotlib.pyplot as plt
from tictoc import tic, toc
from scipy import stats
from sklearn.preprocessing import normalize, MinMaxScaler
import csv

#%% Functions for matchnet architecture

#Function for drop-out in weight matrices
def drop_out(weights, p_conn): 
    N = weights.size
    mask = np.random.choice([0, 1], size=(N,), p=[1-p_conn, p_conn]).reshape((weights.shape[0], weights.shape[1]))
    new_weights = weights*mask
    return new_weights, mask

#First layer is constructed in construct_input(), max filter in output()
def init_layer(pre_layer_size, post_layer_size, p_conn):
    weights, mask = drop_out(np.random.sample((post_layer_size, pre_layer_size)), p_conn)
    delta_weights = np.zeros_like(weights)
    layer = np.zeros(post_layer_size)
    return weights, mask, delta_weights, layer

#Scale transformed vector input between a min and max range
def scale_linear_input(inp_trans, min_range, max_range):
    inp_std = (inp_trans - min(inp_trans)) / (max(inp_trans) - min(inp_trans))
    inp_scaled = inp_std*(max_range - min_range) + min_range
    return inp_scaled

#Function for cosine similarity between vectors
#Used as an extra evaluation tool when judging the comparator performance
def cosine_similarity(inp1, inp2):
    vec_norm = np.linalg.norm(inp1)*np.linalg.norm(inp2)
    cos_corr = np.dot(inp1, inp2)/vec_norm
    return cos_corr

#%% Functions for matchnet input + load the CIFAR data_set

#Get dataset of 10000 normalized CIFAR-10 latent features
def load_cifar_data():
    with open("CIFAR_10_kaggle_feature_2.csv", 'r') as f:
        csv_features = np.array(list(csv.reader(f, delimiter=",")))
    cifar_data = csv_features[1:,1:-2] #with index and labels
    cifar_data_norm = normalize(cifar_data)
    return cifar_data_norm

#Transform the cifar-data into WorkMATe memory size
def cifar_to_memory(cifar_data):
    nl = 30 #from workmate
    W_Sl  = np.random.sample((nl,cifar_data.shape[1]))*(-1)+0.5 #from workmate
    W_Sl, mask = drop_out(W_Sl, 0.1)
    memory_set = [W_Sl.dot(item) for item in cifar_data]
    scaler = MinMaxScaler() #scale between 0 and 1
    cifar_data_mem = scaler.fit_transform(memory_set)
    return cifar_data_mem

def construct_random_input(trial_type, encoding, N, A):
    #Create two random inputs: y (inp1) and z(inp2)
    inp1, inp2 = np.random.sample((N,)), np.random.sample((N,))
    #inp = np.random.choice([0, 1], size=(self.N,)) #The visual input is binary
    #inp = (np.random.sample((self.N,)) - 0.5)*2 #range between -1 and 1
    
    if trial_type == 1: #match
    #there are two options: inp1 and inp2 are exactly equal or inp2 is transformed by a random linear encoding
        if encoding == 'identity':
            inp2 = inp1 
        if encoding == 'linear':
            inp_transform = A.dot(inp1) #dot product with random matrix
            inp2 = scale_linear_input(inp_transform, -1, 1) #normalized to fit between 1 and -1
    return inp1, inp2

def construct_cifar_input(trial_type, encoding, A, cifar_data):
    #Create two random inputs: y (inp1) and z(inp2)
    random_indices = np.random.choice(cifar_data.shape[0], size=2, replace=False)
    inp1, inp2 = cifar_data[random_indices[0],:], cifar_data[random_indices[1],:]
    
    if trial_type == 1: #match
    #there are two options: inp1 and inp2 are exactly equal or inp2 is transformed by a random linear encoding
        if encoding == 'identity':
            inp2 = inp1 
        if encoding == 'linear':
            inp_transform = A.dot(inp1) #dot product with random matrix
            inp2 = scale_linear_input(inp_transform, -1, 1) #normalized to fit between 1 and -1
    return inp1, inp2

def construct_input(trial_type, data_type, encoding, N, A, cifar_data):
    #Create two random inputs: y (inp1) and z(inp2)
    if data_type == 'random':
        inp1, inp2 = np.random.sample((N,)), np.random.sample((N,))
        #inp = np.random.choice([0, 1], size=(self.N,)) #The visual input is binary
        #inp = (np.random.sample((self.N,)) - 0.5)*2 #range between -1 and 1
    elif data_type == 'cifar':
        random_indices = np.random.choice(cifar_data.shape[0], size=2, replace=False)
        inp1, inp2 = cifar_data[random_indices[0],:], cifar_data[random_indices[1],:]
    
    if trial_type == 1: #match
    #there are two options: inp1 and inp2 are exactly equal or inp2 is transformed by a random linear encoding
        if encoding == 'identity':
            inp2 = inp1 
        if encoding == 'linear':
            inp_transform = A.dot(inp1) #dot product with random matrix
            inp2 = scale_linear_input(inp_transform, -1, 1) #normalized to fit between 1 and -1
    return inp1, inp2

#cifar_data = load_cifar_data()
#cifar_data = cifar_to_memory(cifar_data) #transform the dataset to memory inputs

#%% Define the matchnet architecture and learning rules: one input in, x4 out

class MatchNet(object):
    def __init__(self, N=10, encoding='identity', data_type ='random', seed = 30):
        super(MatchNet, self).__init__()
        
        np.random.seed(seed)
        #Matchnet encoding type, data type and constants
        self.encoding = encoding    #encoding can be identity (default) and linear
        self.data_type = data_type  #data can be random (default) and cifar
        self.lr = 0.003
        self.p_eq = 0.5             #probability of equal inputs
        self.alpha_low = 2.7        #sigmoid slope for N < 400
        self.alpha_high = 1.0       #sigmoid slope for N >= 400
        
        #Define matrix transformation for linear encoding
        if encoding == 'linear':
            self.A = np.random.uniform(-1, 1, (self.N, self.N))
        else: self.A = 0
        
        #Define input size N
        if data_type == 'random':
            self.N = N #length input vector, input1 and input2 have the same length
        elif data_type == 'cifar':
            #When CIFAR is chosen, N is overwritten
            #cifar_data_mem = cifar_to_memory(cifar_data)
            inp1, inp2 = construct_input(0, 'cifar', self.encoding, N, self.A, cifar_data)
            self.N = len(inp1) #choose either cifar_data or cifar_data_mem
        
        #Define size next layers
        nx1 = 2*self.N
        nx2 = self.N
        nx3 = round((self.N+1)/2)
        
        #A feedforward network of two learned layers   
        self.W_x1x2, self.mask_W_x1x2, self.delta_W_x1x2, self.x2 = init_layer(nx1, nx2, 0.8)
        self.W_x2x3, self.mask_W_x2x3, self.delta_W_x2x3, self.x3 = init_layer(nx2, nx3, 0.3) 
        
    def step(self):
        x1, trial_type, cosine_corr = self.get_input()
        x2, x3, x4 = self._feedforward(x1)
        self._feedback(x1, x2, x3)
        return x4, trial_type, cosine_corr
        
    def get_input(self):
        #0 is no-match, 1 is match
        trial_type = np.random.choice([0,1], p=[1-self.p_eq, self.p_eq]) #p_eq is match probability
        
        #Get new input
        if self.data_type == 'random':
            inp1, inp2 = construct_random_input(trial_type, self.encoding, self.N, self.A)
        if self.data_type == 'cifar':
            inp1, inp2 = construct_cifar_input(trial_type, self.encoding, self.A, cifar_data)
        x1 = np.concatenate((inp1, inp2)) #The combined activity (length 2N)
        
        #Calculate cosine similarity between incoming vectors for later evaluation
        cosine_corr = cosine_similarity(inp1, inp2)
        
        return x1, trial_type, cosine_corr
    
    def _feedforward(self, x1):
        #Transfer function is the hyperbolic tangent, information is passed forward by a dot product
        x2_in = self.W_x1x2.dot(x1)
        x2 = np.tanh(self.alpha_low*x2_in)
        x3_in = self.W_x2x3.dot(x2)
        x3 = np.tanh(self.alpha_low*x3_in)
        
        #Each third layer neuron estimates the degree of correlation within the input pairs
        #A threshold can be used for binary classification > not needed here for us, we want a match scalar
        #The fourth layer selects the most active third layer neuron
        return x2, x3, max(x3)
    
    def _feedback(self, x1, x2, x3):
        def learn_weights(W, mask, a1, a2):
            #Anti-Hebbian Learning rule
            delta_W = -self.lr*np.outer(a2, a1) #a learning factor for each combination of the pre and postsynaptic neurons
            #Don't forget that not each connection exists >> there is a p_conn below 1! Apply the mask!
            delta_W = delta_W*mask
            W += delta_W
            
            #The weights are normalised to the sum of all connections to one postsynaptic neuron
            #This is local
            for item in range(W.shape[0]):
                norm_factor = np.sqrt(np.sum(W[item]*W[item]))
                W[item] = W[item]/norm_factor
            return W, delta_W
    
        #update the weights by delta using the presynaptic and postsynaptic activity
        self.W_x1x2, self.delta_W_x1x2 = learn_weights(self.W_x1x2, self.mask_W_x1x2, x1, x2)
        self.W_x2x3, self.delta_W_x2x3 = learn_weights(self.W_x2x3, self.mask_W_x2x3, x2, x3)

#%% Function for the training of the Matchnet

def train_matchnet(network, t_max=10000, t_eval=1000):
    eval_data = []
    for i in range(t_max):
        #there is no feedback, no sequentiality, each trial is one independent time step
        x4, trial_type, cosine_corr = matchnet.step()
        
        #print trial_progress
        if i % 1000 == 0:
            print(i)
            
        #save evaluation data
        #save the t_eval results (10%) in paper in a matrix called eval_data
        if i >= (t_max-t_eval):
            data_row = [x4, trial_type, cosine_corr] #save the input vectors, the trial type and the output
            eval_data.append(data_row)
    
    #detangle the list columns in rows
    eval_dt = list(map(list, zip(*eval_data))) #in order: x4 output, trial_type, cosine_corr   
    return matchnet, eval_dt

#%% Function for the performance plot based on the evaluation data 

def plot_eval(x4, trial_type, cos_corr):
    #plot the ordered cosine similarity
    fig, ax = plt.subplots()    
    plt.title('Matchnet evaluation for match (grey) and non-match trials')
    plt.xlabel('Evaluation trials')
    plt.ylabel('Match value')
    trials = range(len(x4))
    ax.set_xlim([0, len(x4)])
    
    #Order cosine corr and order x4 and trial_type in the same manner
    i_sort_coscor = np.argsort(cos_corr)
    cos_cor_sort = np.array(cos_corr)[i_sort_coscor]
    x4_sort = np.array(x4)[i_sort_coscor]  
    
    trial_type_sort = np.array(trial_type)[i_sort_coscor]
    border = np.where(np.array(trial_type_sort)==1)[0][0]
    
    #Plot the average of 10 orange ones in the middle
    bin_means, bin_edges, binnumber = stats.binned_statistic(range(len(x4_sort)),
                x4_sort, statistic='mean', bins=np.array(range(50))*20+20)
    #Plot cosine similarity of the inputs
    plt.plot(trials, cos_cor_sort, '-o', label = 'Cosine similarity') 
    #Plot the match value output of the network
    plt.plot(trials, x4_sort, 'v', label = 'Matchnet')
    #Plot the average match value
    plt.plot(np.array(range(49))*20+20, bin_means, 'k', zorder = 10, label='Matchnet avg')
    #Plot a horizontal line to split the two categories. This is currently done by hand.
    #plt.hlines(0.5, 0, 1000, 'm', label = 'Theta', zorder = 20)
    #Plot the trial_types as a block or as small crosses
    #plt.plot(trials, trial_type_sort, 'k.', label = 'trial type')
    ax.axvspan(border, len(cos_corr), facecolor='grey', alpha=0.5)
    plt.legend(bbox_to_anchor=(1.05, 1.0), loc='upper left')
    plt.show()       

#%% Run the neural comparator

if __name__ == '__main__':
    t_max = 10000          #number of training steps (10**7 in the paper)
    t_eval = 1000          #number of steps that are evaluated (10**6 in paper)
    N = 30                 #length of the input vector

    tic()
    #load CIFAR-10 dataset when used
    cifar_data = load_cifar_data()
    #initialize the network
    #matchnet = MatchNet(N, data_type = 'cifar')
    matchnet = MatchNet(N)  
    #train the network in an unsupervised manner, print every dividable by 10000
    matchnet, eval_dt = train_matchnet(matchnet, t_max, t_eval) 
    #plot the performance
    plot_eval(eval_dt[0], eval_dt[1], eval_dt[2])
    toc()

from __future__ import absolute_import, division, print_function, unicode_literals
import os
import time
import logging
import numpy as np
import pandas as pd
import seaborn as sns

from pandas.plotting import scatter_matrix
import multiprocessing
import matplotlib.pyplot as plt
from functools import partial

from .tools import create_missing_folders, load, load_and_check
from .plotting import draw_weighted_distributions, draw_unweighted_distributions, draw_ROC, resampled_discriminator_and_roc, plot_calibration_curve
from sklearn.model_selection import train_test_split
logger = logging.getLogger(__name__)


class Loader():
    """
    Loading of data.
    """
    def __init__(self):
        super(Loader, self).__init__()

    def loading(
        self,
        folder=None,
        plot=False,
        do = 'qsf',
        x0 = None,
        x1 = None,
        randomize = False,
        save = False,
        correlation = True,
        preprocessing = True,
        nentries = 0,
    ):
        """
        Parameters
        ----------
        folder : str or None
            Path to the folder where the resulting samples should be saved (ndarrays in .npy format). Default value:
            None.
        plot : bool, optional
            make validation plots
        do : str
            Decide what samples to use. Can either be Sherpa Vs Madgraph ('sherpaVsMG5'), Renormalization scale up vs down ('mur') or qsf scale up vs down ('qsf') 
            Default value: 'sherpaVsMG5'
        x0 : dataframe of none
            Either pass a dataframe as in notebook, or None to load sample according to do option. 
        x1 : dataframe of none
            Either pass a dataframe as in notebook, or None to load sample according to do option. 
        randomize : bool, optional
            Randomize training sample. Default value: 
            False
        save : bool, optional
            Save training ans test samples. Default value:
            False
        Returns
        -------
        x : ndarray
            Observables with shape `(n_samples, n_observables)`. The same information is saved as a file in the given
            folder.
        y : ndarray
            Class label with shape `(n_samples, n_parameters)`. `y=0` (`1`) for events sample from the numerator
            (denominator) hypothesis. The same information is saved as a file in the given folder.
        """

        create_missing_folders([folder+do])
        create_missing_folders(['plots'])

        # load samples
        etaJ = [-2.8,-2.4,-2,-1.6,-1.2,-0.8,-0.4,0,0.4,0.8,1.2,1.6,2,2.4,2.8]
        eventVars = ['Njets', 'MET']
        jetVars   = ['Jet_Pt', 'Jet_Eta', 'Jet_Mass', 'Jet_Phi']
        lepVars   = ['Lepton_Pt', 'Lepton_Eta', 'Lepton_Phi']
        vlabels = ['Number of jets', '$\mathrm{p_{T}^{miss}}$ [GeV]', 'Leading jet $\mathrm{p_{T}}$ [GeV]','Leading jet $\eta$', 'Leading jet mass [GeV]','Leading jet $\Phi$', 'Subleading jet $\mathrm{p_{T}}$ [GeV]','Subleading jet $\eta$', 'Subleading jet mass [GeV]','Subleading jet $\Phi$', 'Leading lepton $\mathrm{p_{T}}$ [GeV]','Leading lepton $\eta$','Leading lepton $\Phi$', 'Subleading lepton $\mathrm{p_{T}}$ [GeV]','Subleading lepton $\eta$', 'Subleading lepton $\Phi$']
        jetBinning = [range(0, 2000, 200), etaJ, range(0, 1000, 100), etaJ]
        lepBinning = [range(0, 1000, 100), etaJ, etaJ]
        if do == "ckkw":
            legend = ["CKKW20","CKKW50"]
            x0 = load(f = '/eos/user/m/mvesterb/pmg/ckkwSamples/Sh_228_ttbar_dilepton_EnhMaxHTavrgTopPT_CKKW20.root', events = eventVars, jets = jetVars, leps = lepVars, n = int(nentries), t = 'Tree')
            x1 = load(f = '/eos/user/m/mvesterb/pmg/ckkwSamples/Sh_228_ttbar_dilepton_EnhMaxHTavrgTopPT_CKKW50.root', events = eventVars, jets = jetVars, leps = lepVars, n = int(nentries), t = 'Tree')
        elif do == "qsf":
            legend = ["qsfUp", "qsfDown"]
            x0 = load(f = '/eos/user/m/mvesterb/pmg/qsfSamples/Sh_228_ttbar_dilepton_EnhMaxHTavrgTopPT_QSFDOWN.root', events = eventVars, jets = jetVars, leps = lepVars, n = int(nentries), t = 'Tree')
            x1 = load(f = '/eos/user/m/mvesterb/pmg/qsfSamples/Sh_228_ttbar_dilepton_EnhMaxHTavrgTopPT_QSFUP.root',   events = eventVars, jets = jetVars, leps = lepVars, n = int(nentries), t = 'Tree')
        binning = [range(0, 15, 1), range(0, 1000, 100)]+jetBinning+jetBinning+lepBinning+lepBinning

        if preprocessing:
            factor = 3
            for column in x0.columns:
                upper_lim = x0[column].mean () + x0[column].std () * factor
                upper_lim = x1[column].mean () + x1[column].std () * factor
                lower_lim = x0[column].mean () - x0[column].std () * factor
                lower_lim = x1[column].mean () - x1[column].std () * factor
                x0 = x0[(x0[column] < upper_lim) & (x0[column] > lower_lim)]
                x1 = x1[(x1[column] < upper_lim) & (x1[column] > lower_lim)]
            x0 = x0.round(decimals=2)
            x1 = x1.round(decimals=2)


        if correlation:
            cor0 = x0.corr()
            sns.heatmap(cor0, annot=True, cmap=plt.cm.Reds)
            cor_target = abs(cor0[x0.columns[0]])
            relevant_features = cor_target[cor_target>0.5]
            print("relevant_features ", relevant_features)
            plt.savefig('plots/scatterMatrix_'+do+'.png')
            plt.clf()

        X0 = x0.to_numpy()
        X1 = x1.to_numpy()
        # combine
        x = np.vstack([X0, X1])
        y = np.zeros(x.shape[0])

        y[X0.shape[0] :] = 1.0
        # y shape
        y = y.reshape((-1, 1))
        X_train, X_test, y_train, y_test = train_test_split(x, y, test_size=0.40, random_state=42)
        X_train, X_val,  y_train, y_val =  train_test_split(X_train, y_train, test_size=0.50, random_state=42)
        # save data
        if folder is not None:
            np.save(folder + do + "/x0_train.npy", X0)
            np.save(folder + do + "/x1_train.npy", X1)
            np.save(folder + do + "/x_train.npy", x)
            np.save(folder + do + "/y_train.npy", y)
            np.save(folder + do + "/X_train.npy", X_train)
            np.save(folder + do + "/X_val.npy", X_val)
            np.save(folder + do + "/Y_train.npy", y_train)
            np.save(folder + do + "/Y_val.npy", y_val)

        if plot:
            draw_unweighted_distributions(X0, X1, np.ones(X0[:,0].size), x0.columns, vlabels, binning, legend, save) 
            print("saving plots")
            
        return x, y                                                                                                                                                                                                                                      

    def load_result(
        self,
        x0,
        x1,
        weights = None,
        label = None,
        do = 'qsf',
        save = False,
    ):
        """
        Parameters
        ----------
        weights : ndarray
            r_hat weights:
        Returns
        -------
        """
        eventVars = ['Njets', 'MET']
        jetVars   = ['Jet_Pt', 'Jet_Eta', 'Jet_Mass', 'Jet_Phi']
        lepVars   = ['Lepton_Pt', 'Lepton_Eta', 'Lepton_Phi']
        vlabels = ['Number of jets', '$\mathrm{p_{T}^{miss}}$ [GeV]', 'Leading jet $\mathrm{p_{T}}$ [GeV]','Leading jet $\eta$', 'Leading jet mass [GeV]','Leading jet $\Phi$', 'Subleading jet $\mathrm    {p_{T}}$ [GeV]','Subleading jet $\eta$', 'Subleading jet mass [GeV]','Subleading jet $\Phi$', 'Leading lepton $\mathrm{p_{T}}$ [GeV]','Leading lepton $\eta$','Leading lepton $\Phi$', 'Subleading lepto    n $\mathrm{p_{T}}$ [GeV]','Subleading lepton $\eta$', 'Subleading lepton $\Phi$']
        etaJ = [-2.8,-2.4,-2,-1.6,-1.2,-0.8,-0.4,0,0.4,0.8,1.2,1.6,2,2.4,2.8]
        jetBinning = [range(0, 2000, 200), etaJ, range(0, 1000, 100), etaJ]
        lepBinning = [range(0, 1000, 100), etaJ, etaJ]
        if do == "ckkw":
            legend = ["CKKW20","CKKW50"]
        elif do == "qsf":
            legend = ["qsfUp", "qsfDown"]

        binning = [range(0, 15, 1), range(0, 1000, 100)]+jetBinning+jetBinning+lepBinning+lepBinning
        x0df = load(f = '/eos/user/m/mvesterb/pmg/ckkwSamples/Sh_228_ttbar_dilepton_EnhMaxHTavrgTopPT_CKKW20.root', events = eventVars, jets = jetVars, leps = lepVars, n = 1, t = 'Tree')
        # load samples
        X0 = load_and_check(x0, memmap_files_larger_than_gb=1.0)
        X1 = load_and_check(x1, memmap_files_larger_than_gb=1.0)
        weights = weights / weights.sum() * len(X1)
        # plot ROC curves     
        draw_ROC(X0, X1, weights, label, legend, save)
        # plot reweighted distributions      
        draw_weighted_distributions(X0, X1, weights, x0df.columns, vlabels, binning, label, legend, save) 

    def load_calibration(
        self,
        y_true,
        p1_raw = None,
        p1_cal = None,
        label = None,
        do = 'sherpaVsMG5',
        save = False
    ):
        """
        Parameters
        ----------
        y_true : ndarray
            true targets
        p1_raw : ndarray
            uncalibrated probabilities of the positive class
        p1_cal : ndarray
            calibrated probabilities of the positive class
        Returns
        -------
        """

        # load samples
        y_true  = load_and_check(y_true,  memmap_files_larger_than_gb=1.0)
        plot_calibration_curve(y_true, p1_raw, p1_cal, do, save)                                                                                                                                                                                                                                                                   

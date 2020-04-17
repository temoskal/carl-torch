from __future__ import absolute_import, division, print_function

import logging
import numpy as np
from collections import OrderedDict

from .evaluate import evaluate_ratio_model
from .models import RatioModel
from .functions import get_optimizer, get_loss
from .tools import load_and_check
from .trainers import RatioTrainer
from .base import ConditionalEstimator

try:
    FileNotFoundError
except NameError:
    FileNotFoundError = IOError

logger = logging.getLogger(__name__)
class RatioEstimator(ConditionalEstimator):
    """
    Parameters
    ----------
    features : list of int or None, optional
        Indices of observables (features) that are used as input to the neural networks. If None, all observables
        are used. Default value: None.
    n_hidden : tuple of int, optional
        Units in each hidden layer in the neural networks. 
        Default value: (100,).
    activation : {'tanh', 'sigmoid', 'relu'}, optional
        Activation function. Default value: 'tanh'.
    """

    def train(
        self,
        method,
        x,
        y,
        alpha=1.0,
        optimizer="amsgrad",
        n_epochs=50,
        batch_size=128,
        initial_lr=0.001,
        final_lr=0.0001,
        nesterov_momentum=None,
        validation_split=0.25,
        early_stopping=True,
        scale_inputs=False,
        limit_samplesize=None,
        memmap=False,
        verbose="some",
        scale_parameters=False,
        n_workers=8,
        clip_gradient=None,
        early_stopping_patience=None,
    ):

        """
        Trains the network.
        Parameters
        ----------
        method : str
            The inference method used for training. Allowed values are 'alice', 'alices', 'carl', 'cascal', 'rascal',
            and 'rolr'.
        x : ndarray or str
            Observations, or filename of a pickled numpy array.
        y : ndarray or str
            Class labels (0 = numeerator, 1 = denominator), or filename of a pickled numpy array.
        alpha : float, optional
            Default value: 1.
        optimizer : {"adam", "amsgrad", "sgd"}, optional
            Optimization algorithm. Default value: "amsgrad".
        n_epochs : int, optional
            Number of epochs. Default value: 50.
        batch_size : int, optional
            Batch size. Default value: 128.
        initial_lr : float, optional
            Learning rate during the first epoch, after which it exponentially decays to final_lr. Default value:
            0.001.
        final_lr : float, optional
            Learning rate during the last epoch. Default value: 0.0001.
        nesterov_momentum : float or None, optional
            If trainer is "sgd", sets the Nesterov momentum. Default value: None.
        validation_split : float or None, optional
            Fraction of samples used  for validation and early stopping (if early_stopping is True). If None, the entire
            sample is used for training and early stopping is deactivated. Default value: 0.25.
        early_stopping : bool, optional
            Activates early stopping based on the validation loss (only if validation_split is not None). Default value:
            True.
        scale_inputs : bool, optional
            Scale the observables to zero mean and unit variance. Default value: True.
        memmap : bool, optional.
            If True, training files larger than 1 GB will not be loaded into memory at once. Default value: False.
        verbose : {"all", "many", "some", "few", "none}, optional
            Determines verbosity of training. Default value: "some".
        Returns
        -------
            None
        """

        logger.info("Starting training")
        logger.info("  Method:                 %s", method)
        logger.info("  Batch size:             %s", batch_size)
        logger.info("  Optimizer:              %s", optimizer)
        logger.info("  Epochs:                 %s", n_epochs)
        logger.info("  Learning rate:          %s initially, decaying to %s", initial_lr, final_lr)
        if optimizer == "sgd":
            logger.info("  Nesterov momentum:      %s", nesterov_momentum)
        logger.info("  Validation split:       %s", validation_split)
        logger.info("  Early stopping:         %s", early_stopping)
        logger.info("  Scale inputs:           %s", scale_inputs)
        if limit_samplesize is None:
            logger.info("  Samples:                all")
        else:
            logger.info("  Samples:                %s", limit_samplesize)

        # Load training data
        logger.info("Loading training data")
        memmap_threshold = 1.0 if memmap else None
        x = load_and_check(x, memmap_files_larger_than_gb=memmap_threshold)
        y = load_and_check(y, memmap_files_larger_than_gb=memmap_threshold)

        # Infer dimensions of problem
        n_samples = x.shape[0]
        n_observables = x.shape[1]
        logger.info("Found %s samples with %s observables", n_samples, n_observables)

        # Scale features
        if scale_inputs:
            self.initialize_input_transform(x, overwrite=False)
            x = self._transform_inputs(x)
        else:
            self.initialize_input_transform(x, False, overwrite=False)

        # Features
        if self.features is not None:
            x = x[:, self.features]
            logger.info("Only using %s of %s observables", x.shape[1], n_observables)
            n_observables = x.shape[1]

        # Check consistency of input with model
        if self.n_observables is None:
            self.n_observables = n_observables

        if n_observables != self.n_observables:
            raise RuntimeError(
                "Number of observables does not match model: {} vs {}".format(n_observables, self.n_observables)
            )

        # Data
        data = self._package_training_data(method, x, y)
        data_val = None
        # Create model
        if self.model is None:
            logger.info("Creating model")
            self._create_model()

        # Losses
        loss_functions, loss_labels, loss_weights = get_loss(method + "2", alpha)
        # Optimizer
        opt, opt_kwargs = get_optimizer(optimizer, nesterov_momentum)

        # Train model
        logger.info("Training model")
        trainer = RatioTrainer(self.model, n_workers=n_workers)
        result = trainer.train(
            data=data,
            data_val=data_val,
            loss_functions=loss_functions,
            loss_weights=loss_weights,
            loss_labels=loss_labels,
            epochs=n_epochs,
            batch_size=batch_size,
            optimizer=opt,
            optimizer_kwargs=opt_kwargs,
            initial_lr=initial_lr,
            final_lr=final_lr,
            validation_split=validation_split,
            early_stopping=early_stopping,
            verbose=verbose,
            clip_gradient=clip_gradient,
            early_stopping_patience=early_stopping_patience,
        )
        print("results", result)
        return result

    def evaluate_log_likelihood_ratio(self, x):
        """
        Evaluates the log likelihood ratio as a function of the observation x, the numerator hypothesis theta0, and
        the denominator hypothesis theta1.
        Parameters
        ----------
        x : str or ndarray
            Observations or filename of a pickled numpy array.
        test_all_combinations : bool, optional
            If False, the number of samples in the observable and theta
            files has to match, and the likelihood ratio is evaluated only for the combinations
            `r(x_i | theta0_i, theta1_i)`. If True, `r(x_i | theta0_j, theta1_j)` for all pairwise combinations `i, j`
            are evaluated. Default value: True.
        Returns
        -------
        log_likelihood_ratio : ndarray
            The estimated log likelihood ratio. If test_all_combinations is True, the result has shape
            `(n_thetas, n_x)`. Otherwise, it has shape `(n_samples,)`.
        """
        if self.model is None:
            raise ValueError("No model -- train or load model before evaluating it!")

        # Load training data
        logger.debug("Loading evaluation data")
        x = load_and_check(x)

        # Scale observables
        x = self._transform_inputs(x)

        # Restrict features
        if self.features is not None:
            x = x[:, self.features]


        logger.debug("Starting ratio evaluation")
        _, r_hat = evaluate_ratio_model(
            model=self.model,
            method_type="double_parameterized_ratio",
            xs=x,
        )

        logger.debug("Evaluation done")
        return r_hat

    def evaluate(self, *args, **kwargs):
        return self.evaluate_log_likelihood_ratio(*args, **kwargs)

    def _create_model(self):
        self.model = RatioModel(
            n_observables=self.n_observables,
            n_hidden=self.n_hidden,
            activation=self.activation,
            dropout_prob=self.dropout_prob,
        )

    @staticmethod
    def _package_training_data(method, x,  y):
        data = OrderedDict()
        data["x"] = x
        data["y"] = y
        return data

    def _wrap_settings(self):
        settings = super(RatioEstimator, self)._wrap_settings()
        settings["estimator_type"] = "double_parameterized_ratio"
        return settings

    def _unwrap_settings(self, settings):
        super(RatioEstimator, self)._unwrap_settings(settings)

        estimator_type = str(settings["estimator_type"])
        if estimator_type != "double_parameterized_ratio":
            raise RuntimeError("Saved model is an incompatible estimator type {}.".format(estimator_type))


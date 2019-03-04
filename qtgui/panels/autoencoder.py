"""
File: logging.py
Author: Ulf Krumnack
Email: krumnack@uni-osnabrueck.de
Github: https://github.com/krumnack
"""
# FIXME[hack]: this is just using a specific keras network as proof of
# concept. It has to be modularized and integrated into the framework

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QPushButton, QSpinBox, QLineEdit,
                             QVBoxLayout, QHBoxLayout)

from .panel import Panel
from qtgui.widgets.matplotlib import QMatplotlib
from qtgui.widgets.training import QTrainingBox

import numpy as np
import matplotlib.pyplot as plt
import os

from qtgui.utils import QObserver

from toolbox import toolbox
from tools.train import Training, Trainer

# FIXME[hack]
from network.keras import Training as KerasTraining

class AutoencoderPanel(Panel, QObserver, toolbox.Observer, Training.Observer):
    """A panel displaying autoencoders.

    Attributes
    ----------
    _autoencoder: Network
        A network trained as autoencoder.
    """

    def __init__(self, parent=None):
        """Initialization of the LoggingPael.

        Parameters
        ----------
        parent  :   QWidget
                    The parent argument is sent to the QWidget constructor.
        """
        super().__init__(parent)
        self._autoencoder = None
        self._autoencoderController = None
        self._training = KerasTraining()
        self._trainer = Trainer(self._training)

        self._cache = {}
        
        # FIXME[hack]: we need a better data concept ...
        self._training.hack_load_mnist()
        self._imageShape = (28, 28)

        self._initUI()
        self._layoutComponents()
        self._connectComponents()

        self.autoencoderController = AutoencoderController()

        # Training parameters
        self._spinboxEpochs.setValue(4)

        self.observe(toolbox)
        self._enableComponents()

        # 
        self._trainingBox.observe(self._training)
        self.observe(self._training)

    # FIXME[hack]: we need a better data concept ...
    @property
    def inputs(self):
        return None if self._training is None else self._training._x_test

    @property
    def labels(self):
        return None if self._training is None else self._training._y_test
    
    def _initUI(self):
        """Add the UI elements

            * The ``QLogHandler`` showing the log messages

        """
        #
        # Controls
        #
        self._buttonCreateModel = QPushButton("Create")
        self._buttonTrainModel = QPushButton("Train")

        self._editWeightsFilename = QLineEdit('vae_mlp_mnist.h5')

        self._buttonLoadModel = QPushButton("Load")
        self._buttonSaveModel = QPushButton("Save")
        self._buttonPlotModel = QPushButton("Plot Model")
        self._buttonPlotCodeDistribution = QPushButton("Code Distribution")
        self._buttonPlotCodeVisualization = QPushButton("Code Visualization")
        self._buttonPlotReconstruction = QPushButton("Plot Reconstruction")
        self._buttonPlotReconstruction.clicked.\
            connect(self._onPlotReconstruction)

        self._spinboxEpochs = QSpinBox()
        self._spinboxEpochs.setRange(1, 50)

        self._spinboxBatchSize = QSpinBox()

        self._spinboxGridSize = QSpinBox()
        self._spinboxGridSize.setValue(10)
        self._spinboxGridSize.setRange(4,50)
        self._spinboxGridSize.valueChanged.\
            connect(self._onPlotCodeVisualization)

        #
        # Plots
        #
        self._trainingBox = QTrainingBox()
        self._pltIn = QMatplotlib()
        self._pltCode = QMatplotlib()
        self._pltOut = QMatplotlib()

    def _connectComponents(self):
        self._buttonCreateModel.clicked.connect(self._trainer._hackNewModel)
        self._buttonTrainModel.clicked.connect(self._trainer.start)
        self._spinboxEpochs.valueChanged.connect(self._trainer.set_epochs)
        self._spinboxBatchSize.valueChanged.\
            connect(self._trainer.set_batch_size)
        self._buttonPlotCodeDistribution.clicked.\
            connect(self._onPlotCodeDistribution)
        self._buttonPlotCodeVisualization.clicked.\
            connect(self._onPlotCodeVisualization)

    def _layoutComponents(self):
        """Layout the UI elements.

            * The ``QLogHandler`` displaying the log messages

        """
        plotBar = QHBoxLayout()
        plotBar.addWidget(self._trainingBox)

        displayBox = QHBoxLayout()
        displayBox.addWidget(self._pltCode)
        displayInOut = QVBoxLayout()
        displayInOut.addWidget(self._pltIn)
        displayInOut.addWidget(self._pltOut)
        displayBox.addLayout(displayInOut)
        plotBar.addLayout(displayBox)

        buttonBar = QHBoxLayout()
        buttonBar.addWidget(self._buttonCreateModel)
        buttonBar.addWidget(self._spinboxEpochs)
        buttonBar.addWidget(self._spinboxBatchSize)
        buttonBar.addWidget(self._buttonTrainModel)
        buttonBar.addWidget(self._editWeightsFilename)
        buttonBar.addWidget(self._buttonLoadModel)
        buttonBar.addWidget(self._buttonSaveModel)
        buttonBar.addWidget(self._buttonPlotModel)
        buttonBar.addWidget(self._buttonPlotCodeDistribution)
        buttonBar.addWidget(self._spinboxGridSize)
        buttonBar.addWidget(self._buttonPlotCodeVisualization)
        buttonBar.addWidget(self._buttonPlotReconstruction)

        layout = QVBoxLayout()
        layout.addLayout(plotBar)
        layout.addLayout(buttonBar)
        self.setLayout(layout)

    def _enableComponents(self, running=False):
        enabled = ((self._autoencoder is None) and  # or not self._autoencoder.busy
                   (self._autoencoderController is None or
                    not self._autoencoderController.busy))
        self._buttonCreateModel.setEnabled(enabled)
        
        enabled = self._autoencoder is not None  # and not self._autoencoder.busy
        self._buttonTrainModel.setEnabled(enabled)
        enabled = enabled and not running
        self._spinboxEpochs.setEnabled(enabled)
        self._spinboxBatchSize.setEnabled(enabled)
        enabled = (self._autoencoderController is not None and
                   not self._autoencoderController.busy)
        for w in (self._buttonLoadModel, self._buttonSaveModel,
                  self._buttonPlotModel,
                  self._buttonPlotCodeDistribution,
                  self._spinboxGridSize, self._buttonPlotCodeVisualization,
                  self._buttonPlotReconstruction):
            w.setEnabled(enabled)

    @property
    def autoencoder(self):
        return self._autoencoder

    @autoencoder.setter
    def autoencoderController(self, autoencoder):
        self.autoencoder = autoencoder

    @property
    def autoencoderController(self):
        return self._autoencoderController

    @autoencoderController.setter
    def autoencoderController(self, controller):
        self._autoencoderController = controller
        self._spinboxBatchSize.setRange(*controller.batch_size_range)
        slot = AutoencoderController.batch_size.fset.__get__(controller)
        self._spinboxBatchSize.valueChanged.connect(slot)
        slot = lambda checked: \
            controller.load_model(self._editWeightsFilename.text())
        self._buttonLoadModel.clicked.connect(slot)
        slot = lambda checked: \
            controller.save_model(self._editWeightsFilename.text())
        self._buttonSaveModel.clicked.connect(slot)
        slot = lambda checked: controller.plot_model()
        self._buttonPlotModel.clicked.connect(slot)
        self.autoencoderControllerChanged(controller, controller.Change.all())
        self.observe(controller)
        
    def _onPlotCodeDistribution(self, codes=None):
        """Display a 2D plot of the digit classes in the latent space.

        Arguments
        ---------
        data (tuple): test data and label
        batch_size (int): prediction batch size
        model_name (string): which model is using this function
        """
        if isinstance(codes, np.ndarray):
            self._cache['codes'] = codes
        else:
            codes = self._cache.get('codes', None)
            
        #z_mean = self._autoencoderController.code_means
        labels = self.labels

        if codes is None:
            inputs = self.inputs
            if inputs is not None:
                self._autoencoderController.\
                    encode(inputs, async_callback=self._onPlotCodeDistribution)

            self._pltCode.noData()
        else:
            with self._pltCode as ax:
                if labels is None:
                    ax.scatter(codes[:, 0], codes[:, 1])
                else:
                    ax.scatter(codes[:, 0], codes[:, 1], c=labels)
                    # plt.colorbar()
                ax.set_xlabel("z[0]")
                ax.set_ylabel("z[1]")

    def _onPlotCodeVisualization(self, images=None):
        """Plot visualization of the code space.

        Create a regular grid in code space and decode the code points
        on this grid. Construct an image showing the decoded images
        arranged on that grid.
        """

        if (isinstance(images, np.ndarray) and
            'visualization_n' in self._cache):
            # we have computed new images: redraw the figure
            n = self._cache['visualization_n']
            shape = self._imageShape
            figure = np.zeros((shape[0] * n, shape[1] * n))
            for i, (x, y) in enumerate(np.ndindex(n, n)):
                figure[y * shape[0]: (y+1) * shape[0],
                       x * shape[1]: (x+1) * shape[1]] = \
                       images[i].reshape(shape)
        elif (not isinstance(images, int) and  # triggered by _spinboxGridSize
              'visualization_figure' in self._cache and
              'visualization_n' in self._cache):
            # we have cached the figure
            n = self._cache['visualization_n']
            shape = self._imageShape
            figure = self._cache['visualization_figure']
        else:
            # we have to (re)compute the figure:
            n = self._spinboxGridSize.value()
            figure = None

        grid_x = np.linspace(-4, 4, n)
        grid_y = np.linspace(-4, 4, n)

        if figure is None:
            # linearly spaced coordinates corresponding to the 2D plot
            # of digit classes in the latent space
            meshgrid = np.meshgrid(grid_x, grid_y)
            grid = np.asarray([meshgrid[0].flatten(), meshgrid[1].flatten()]).T
            batch_size = self._spinboxBatchSize.value()
            self._cache['visualization_n'] = n
            self._cache.pop('visualization_image', None)
            self._autoencoderController.\
                decode(grid, async_callback=self._onPlotCodeVisualization)
            self._pltCode.noData()
        else:
            start_range = shape[0] // 2
            end_range = n * shape[0] - start_range + 1
            pixel_range = np.arange(start_range, end_range, shape[0])
            sample_range_x = np.round(grid_x, 1)
            sample_range_y = np.round(grid_y, 1)
            with self._pltCode as ax:
                ax.imshow(figure, cmap='Greys_r')
                ax.set_xticks(pixel_range, minor=False)
                ax.set_xticklabels(sample_range_x, fontdict=None, minor=False)
                ax.set_yticks(pixel_range, minor=False)
                ax.set_yticklabels(sample_range_y, fontdict=None, minor=False)
                ax.set_xlabel("z[0]")
                ax.set_ylabel("z[1]")
                ax.set_title("Code Layer")

    def _onPlotReconstruction(self, data=None):
        """Plot examples of the reconstructions done by the autoencoder.  This
        will display the input image next to the reconstruction as
        well as a difference image.
        """
        inputs = self.inputs
        labels = self.labels

        if isinstance(data, bool):  # invoced from GUI: select new index
            self._cache['reconstruction_index'] = \
                -1 if inputs is None else np.random.randint(len(inputs))
        elif isinstance(data, np.ndarray):
            self._cache['reconstruction_data'] = data

        index = self._cache.get('reconstruction_index', -1)
        reconstructions = self._cache.get('reconstruction_data', None)
        if reconstructions is None and inputs is not None:
            self._autoencoderController.\
                reconstruct(inputs, async_callback=self._onPlotReconstruction)

        if index == -1:
            plt.noData()
        else:
            input_image = inputs[index].reshape(self._imageShape)
            input_label = None if labels is None else labels[index].argmax()
            with self._pltIn as ax:
                ax.imshow(input_image, cmap='gray')
                ax.set_title(f"input: test sample {index}" +
                             ("" if input_label is None else
                              f" ('{input_label}')"))

        outputs = reconstructions
        if outputs is None or index ==-1:
            self._pltOut.noData()
            self._pltCode.noData()
        else:
            output_image = outputs[index].reshape(self._imageShape) 
            with self._pltOut as ax:
                ax.imshow(output_image, cmap='gray')
                ax.set_title("Reconstruction")

            with self._pltCode as ax:
                ax.imshow((input_image-output_image), cmap='seismic')
                ax.set_title("Differences")

    def toolboxChanged(self, toolbox, change):
        self._enableComponents(toolbox.locked())

    def trainingChanged(self, training, change):
        if 'training_changed' in change and self._trainer is not None:
            self._buttonTrainModel.clicked.disconnect()
            if training.running:
                self._buttonTrainModel.setText("Stop")
                self._buttonTrainModel.clicked.connect(self._trainer.stop)
            else:
                self._buttonTrainModel.setText("Train")
                self._buttonTrainModel.clicked.connect(self._trainer.start)

        if 'network_changed' in change:
            self._autoencoder = training.network
            self._autoencoderController.set_autoencoder(training.network)
            self._enableComponents()

    def autoencoderControllerChanged(self, controller, change):
        if 'busy_changed' in change:
            self._enableComponents()

        if 'network_changed' in change:
            self._enableComponents()

        if 'weights_changed' in change:
            self._cache = {}

        if 'parameter_changed' in change:
            self._spinboxBatchSize.setValue(controller.batch_size)


        
from base.controller import Controller, run
import util

class AutoencoderController(Controller,
                            method='autoencoderControllerChanged',
                            changes=['network_changed', 'weights_changed',
                                     'data_changed', 'parameter_changed']):
    # 'network_changed': network was changed:
    # 'weights_changed': network weights were changed
    # 'data_changed': a new dataset is provided
    # 'parameter_changed': hyperparmeter changed (batch_size)

    def __init__(self, autoencoder=None):
        super().__init__(util.runner)  # FIXME[hack]
        self.set_autoencoder(autoencoder)

        self.batch_size_range = 1, 256
        self._batch_size = 128

        self.epochs_range = 1, 50
        self._epochs = 5

    def set_autoencoder(self, autoencoder):
        self._autoencoder = autoencoder

    @property
    def batch_size(self):
        return self._batch_size

    @batch_size.setter
    def batch_size(self, size: int):
        if self.batch_size_min <= size <= self.batch_size_max:
            if self._batch_size != size:
                self._batch_size = size
                self.change('parameter_changed')
        else:
            raise ValueError(f"Invalid batch size {size}:"
                             f"allowed range is from {self.batch_size_min}"
                             f"to {self.batch_size_max}")

    @property
    def batch_size_range(self):
        return (self.batch_size_min, self.batch_size_max)

    @batch_size_range.setter
    def batch_size_range(self, batch_size_range):
        self.batch_size_min, self.batch_size_max = batch_size_range

    @property
    def inputs(self):
        return self._input_data

    @property
    def labels(self):
        return self._input_labels

    @property
    def code_means(self):
        return self._z_mean

    @property
    def codes(self):
        return self._code_data

    @property
    def outputs(self):
        return self._output_data

    def set_input_data(self, data, labels=None):
        self._input_data = data
        self._input_labels = labels
        self._z_mean = None
        self.set_code_data(None)

    def set_code_data(self, data, labels=None):
        self._code_data = data
        self._code_labels = labels
        self.set_output_data(None)

    def set_output_data(self, data, labels=None):
        self._output_data = data
        self._output_labels = labels


    @run
    def load_model(self, filename):
        self._autoencoder.load(filename)
        
    @run
    def save_model(self, checked: bool=False):
        self._autoencoder.save(self._weights_file)

    def plot_model(self):
        pass

    @run
    def encode(self, inputs):
        return self._autoencoder.encode(inputs, self._batch_size)

    @run
    def decode(self, codes):
        return self._autoencoder.decode(codes, self._batch_size)

    @run
    def reconstruct(self, inputs):
        return self._autoencoder.reconstruct(inputs, self._batch_size)

    @run
    def sample(self):
        self._z_mean = None
        self.change('data_changed')
        self._output_data = self._autoencoder.reconstruct(self._input_data,
                                                          self._batch_size)
        self.change('data_changed')

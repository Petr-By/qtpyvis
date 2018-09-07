'''
File: maximization.py
Author: Ulf Krumnack, Antonia Hain
Email: krumnack@uni-osnabrueck.de
Github: https://github.com/krumnack
'''

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QGroupBox, QSplitter

from qtgui.widgets.maximization import QMaximizationConfig
from .panel import Panel
import controller
from observer import Observer

import numpy as np


class MaximizationPanel(Panel, Observer):
    '''A complex panel containing elements to configure the
    activation maximization of individual unites.

    Attributes
    ----------
    _network_map    :   dict A dictionary mapping the strings displayed in the network selector
                        dropdown to actual network objects.
    '''

    _network_map    :   dict = {}

    def __init__(self, model, parent=None):
        '''Initialization of the ActivationsPael.

        Parameters
        ----------
        parent  :   QWidget
                    The parent argument is sent to the QWidget constructor.
        model   :   model.Model
                    The backing model. Communication will be handled by a
                    controller.
        '''
        from controller import ActivationsController
        super().__init__(parent)
        self.initUI()
        self.setController(ActivationsController(model))

    
    def setController(self, controller):
        super().setController(controller)
        controllable_widgets = [self._maximization_config_view]
        for widget in controllable_widgets:
            widget.setController(controller)


    def initUI(self):
        '''Add additional UI elements

            * The ``QActivationView`` showing the unit activations on the left

        '''
        super().initUI()


        #######################################################################
        #                            Configuration                            #
        #######################################################################
        # QMaximizationConfig: a widget to configure the maximization process
        self._maximization_config_view = QMaximizationConfig()

        # FIXME[layout]
        self._maximization_config_view.setMinimumWidth(200)
        self._maximization_config_view.resize(400, self._maximization_config_view.height())

        config_layout = QVBoxLayout()
        config_layout.addWidget(self._maximization_config_view)

        config_box = QGroupBox('Configuration')
        config_box.setLayout(config_layout)

        layout = QHBoxLayout()
        layout.addWidget(config_box)
        self.setLayout(layout)
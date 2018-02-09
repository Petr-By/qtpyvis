from qtgui.datasources import DataSource, InputData
from PyQt5.QtWidgets import QWidget, QFileDialog
from scipy.misc import imread
from os.path import join
from os import listdir

class DataDirectory(DataSource):
    '''A data directory contains data entries (e.g., images), in
    individual files. Each files is only read when accessed.

    Attributes
    ----------
    _dirname    :   str
                    A directory containing input data files. Can be None.


    _filenames  :   list
                    A list of filenames in the data directory. Will be None if
                    no directory was selected. An empty list indicates that no
                    suitable files where found in the directory.
    '''
    _dirname: str = None
    _filenames: list = None

    def __init__(self, dirname: str=None):
        '''Create a new DataDirectory

        Parameters
        ----------
        dirname :   str
                    Name of the directory with files
        '''
        super().__init__()
        self.setDirectory(dirname)

    def setDirectory(self, dirname: str):
        '''Set the directory to load from

        Parameters
        ----------
        dirname :   str
                    Name of the directory with files
        '''
        self._dirname = dirname
        if self._dirname is None:
            self._filenames = None
        else:
            self._filenames = [f for f in listdir(self._dirname)
                               if isfile(join(self._dirname, f))]

    def getDirectory(self) -> str:
        return self._dirname

    def __getitem__(self, index):
        if not self._filenames:
            return None, None
        else:
            # TODO: This can be much improved by caching and/or prefetching
            filename = self._filenames[index]
            data = imread(join(self._dirname, filename))
            return InputData(data, filename)

    def __len__(self):
        if not self._filenames:
            return 0
        return len(self._filenames)

    def selectDirectory(self, parent: QWidget=None):
        dirname = QFileDialog.getExistingDirectory(parent, 'Select Directory')
        if not dirname or not isdir(dirname):
            raise FileNotFoundError('%s is not a directory.' % dirname)
        else:
            self.setDirectory(dirname)



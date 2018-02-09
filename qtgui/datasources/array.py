import numpy as np
from qtgui.datasources import DataSource, InputData

class DataArray(DataSource):
    '''A ``DataArray`` the stores all entries in an array (like the MNIST
    character data). That means that all entries will have the same sizes.

    Attributes
    ----------
    _array  :   np.ndarray
                An array of input data. Can be None.
    '''
    _array: np.ndarray = None

    def __init__(self, array: np.ndarray=None, description: str=None):
        '''Create a new DataArray

        Parameters
        ----------
        array   :   np.ndarray
                    Numpy data array
        description :   str
                        Description of the data set

        '''
        super().__init__(description)
        if array is not None:
            self.setArray(array, description)

    def setArray(self, array, description='array'):
        '''Set the array of this DataSource.

        Parameters
        ----------
        array   :   np.ndarray
                    Numpy data array
        description :   str
                        Description of the data set
        '''
        self._array = array
        self._description = description

    def __getitem__(self, index: int):
        if self._array is None or index is None:
            return None, None
        data = self._array[index]
        info = 'Image ' + str(index) + ' from ' + self._description
        return InputData(data, info)

    def __len__(self):
        if self._array is None:
            return 0
        return len(self._array)



# FIXME[todo]:
# * finish refactoring (get & fetch)
#   - label
#   - batch
# * documentation
# * name and description
# * availability and download/install
# FIXME[warning]: doc/source/datasource.rst 6
# WARNING: duplicate object description of datasource.datasource,
# other instance in datasource, use :noindex: for one of them
"""
.. moduleauthor:: Ulf Krumnack

.. module:: datasource.datasource


This module contains abstract definitions of :py:class:`Datasource`\\ s.
All basic functionality a datasource may have should be specified in
in this module.

A :py:class:`Datasource` realizes two modes of
obtaining data: synchronous and asynchronous. The asynchronous methods
are prefixed by 'fetch': These methods will immediatly return, while
running a background thread to obtain the data. Once data are available,
observers will receive a `data_changed` notification.

Other modules implementing access to :py:class:`Datasource`\\ s
should rely on the APIs defined here. Such modules include.
* qtgui.widgets.datasource


* blocking (sync) vs. non-blocking (async)
* non-busy vs. busy

Implementation Guides
=====================

* Changing the order of superclasses should not affect implementation
  (e.g. class MyData(Labeled, Timestamped) should not
  Hence use dict instead of tuple as return type for get_data
  (named.)

Abstract classes 1
------------------
Provide a new data access mechanism x (like index, random, ...)
* may implement a preparation mechanism
* provide public API methods fetch_x() and get_x()
* overwrite private method get(meta, done:bool, x=x):
  - should invoke self._get_x() or self._get_x_batch()
  - should call super()._get(done=True)
  - should provide dummy implementation of _get_x_batch()
  problem: _get_batch() should be more efficient than
     repeated _get()
     -> _get_x should return data instead of setting meta properties
        -> but how to deal with additional information like label?

Worker classes
--------------
* should implement _get_x() (and optionally _get_x_batch()) methods
  according to their type (usually it is sufficient to look at the
  direct superclass)
* the result of the _get_x() method depends on the type:
  - simple classes just return data
  - labeled classes would return pairs (data, label)
    (or better: dict {data: data, label: label})
* the result of the _get_batch_x() method also depends on the type:
  - it should return the same dict as _get_x(), but with values
    being lists or arrays of same length

"""

# standard imports
from typing import Sequence, Union, Tuple
from abc import ABC, abstractmethod
import os
import time
import pickle
import random
import logging
import threading

# third party imports
import numpy as np

# toolbox imports
from .meta import Metadata
from .data import Data
from base import Preparable, FailableObservable, MetaRegister, change, busy
from util.image import imread

# logging
LOG = logging.getLogger(__name__)


class Datasource(Preparable, FailableObservable,
                 method='datasource_changed',
                 changes=['state_changed', 'metadata_changed',
                          'data_changed', 'batch_changed'],
                 metaclass=MetaRegister):  # FIXME[todo]: ABCMetaRegister
    # For some (unknown) reason, pylint currently complains when
    # not overriding an abstract method (load_datapoint_from_file)
    # pylint: disable=abstract-method
    """.. :py:class:: Datasource

    An abstract base class for different types of data sources.

    There are different APIs for navigating in a datasource, depending
    on what that datasource supports:

    array-like navigation: individual elements of a data source can be
    accessed using an array-like notation.

    random selection: select a random element from the dataset.

    Attributes
    ----------
    _description : str
        Short description of the dataset

    Changes
    -------
    state_changed:
        The state of the Datasource has changed (e.g. data were downloaded,
        loaded/unloaded, unprepared/prepared, etc.)
    data_changed:
        The data have changed (e.g. by invoking some fetch ... method).
    batch_changed:
        The batch has changed (e.g. by invoking the fetch_batch method).
    metadata_changed:

    """

    # FIXME[todo]: The datasource may also be in a failed state,
    # e.g. when trying to fetch images from a webcam which is disconnected.
    # maybe introduce a StatefulObservable with the following states:
    #  - prepared/unprepared
    #  - busy
    #  - failed
    # Adding a change: state_changed
    # Adding a property: state:
    # Adding a property: state_description: str
    # But: some states may be more permanent then others:
    #  - e.g. prepared may be interrupted by busy states, e.g. when
    #    fetching data
    #  - failed may indicate that preparation failed (the resource
    #    will be in an unprepared state) or that fetching failed
    #    (in which case it may still remain in the prepared state)

    _id: str = None
    _metadata = None

    # FIXME[hack]: we should put this in the util package!
    try:
        from appdirs import AppDirs
        appname = "deepvis"  # FIXME: not the right place to define here!
        appauthor = "krumnack"
        _appdirs = AppDirs(appname, appauthor)
    except ImportError:
        _appdirs = None
        LOG.warning(
            "--------------------------------------------------------------\n"
            "info: module 'appdirs' is not installed.\n"
            "We can live without it, but having it around will provide\n"
            "additional features.\n"
            "See: https://github.com/ActiveState/appdirs\n"
            "--------------------------------------------------------------\n")

    def __init__(self, description: str = None, **kwargs) -> None:
        """Create a new Datasource.

        Parameters
        ----------
        description :   str
                        Description of the dataset
        """
        super().__init__(**kwargs)
        self._description = (self.__class__.__name__ if description is None
                             else description)
        self._data = None

    @property
    def name(self):
        """Get the name of this :py:class:`Datasource` to be
        presented to the user.
        """
        return f"{self.key}"

    #
    # Preparation
    #

    def _post_prepare(self):
        """After preparing the :py:class:`Datasource`, we will
        fetch the first datapoint.
        """
        # FIXME[concept]: this may be useful in interactive settings but
        # may not be desirable in scripted and other applications ...
        self.fetch()

    def _unprepare(self):
        self.unfetch()
        super()._unprepare()

    ##
    # Data
    ##

    def get_data(self, batch: int = None, **kwargs) -> Data:
        data = Data(datasource=self, batch=batch)
        data.add_attribute('datasource', self)
        data.add_attribute('datasource_argument')
        data.add_attribute('datasource_value')
        LOG.debug("Datasource[%s].get_data(%s)", self, kwargs)
        self._get_meta(data, **kwargs)
        if data.is_batch:
            self._get_batch(data, **kwargs)
            LOG.debug("Datasource[%s].get_batch(): %s", self, data)
        else:
            self._get_data(data, **kwargs)
            LOG.debug("Datasource[%s].get_data(): %s", self, data)
        return data

    def _get_data(self, data: Data, **kwargs) -> None:
        """Get data from this :py:class:`Datasource`.
        """
        if not data:
            LOG.debug("Datasource[%r]._get_default(kwargs=%r): %r",
                      type(self), kwargs, data)
            self._get_default(data, **kwargs)
        LOG.debug(f"Datasource[{self}]._get_data({kwargs}): {data}")

    def _get_batch(self, data, **kwargs) -> None:
        """Get data from this :py:class:`Datasource`.
        """
        if not data:
            # initialize all batch attributes
            data.initialize_attributes(batch=True)
            # get data for each item of the batch
            for item in data:
                self._get_data(item, **kwargs)

    def _get_meta(self, data, **kwargs) -> None:
        pass

    @abstractmethod
    def _get_default(self, data, **kwargs) -> None:
        """The default method for getting data from this
        :py:class:`Datasource`. This method should be implemented by
        all subclases of :py:class:`Datasource`.

        """
        pass  # to be implemented by subclasses

    # @abstractmethod
    def _get_data_old(self) -> np.ndarray:  # FIXME[old]
        """The actual implementation of the :py:meth:`data` property
        to be overwritten by subclasses.

        It can be assumed that a data point has been fetched when this
        method is invoked.
        """
        pass
        raise NotImplementedError(f"{self.__class__.__name__} claims to be "
                                  "a Datasource, but it does not "
                                  "implement the '_get_data' method")

    def _get_batch_data_old(self) -> np.ndarray:  # FIXME[old]
        """The actual implementation of the :py:meth:`batch_data`
        to be overwritten by subclasses.

        It can be assumed that a batch has been fetched when this
        method is invoked.
        """
        pass
        raise NotImplementedError(f"{self.__class__.__name__} claims to be "
                                  "a Datasource, but it does not "
                                  "implement the '_get_batch_data' method")

    #
    # Fetching
    #

    @property
    def fetched(self) -> bool:
        """Check if data have been fetched and are now available.
        If so, :py:meth:`data` should deliver this data.
        """
        return self._data is not None

    @property
    def data(self) -> Data:
        """Get the last data that was fetched from this :py:class:`Datasource`.
        """
        #if not self.fetched:
        #    raise RuntimeError("No data has been fetched on Datasource "
        #                       f"{self.__class__.__name__}")
        return self._data

    @property
    def batch_data_old(self) -> np.ndarray:  # FIXME[old]
        """Get the currently selected batch.
        """
        return self._get_batch_data()

    @property
    def metadata_old(self):  # FIXME[old]
        """Metadata for the currently selected data.
        """
        if not self.fetched:
            raise RuntimeError("No (meta)data has been fetched "
                               f"on Datasource {self.__class__.__name}")
        return self._metadata

    @busy("fetching")
    def fetch(self, **kwargs):
        """Fetch a new data point from the datasource. After fetching
        has finished, which may take some time and may be run
        asynchronously, this data point will be available via the
        :py:meth:`data` property. Observers will be notified by
        by 'data_changed'.

        Arguments
        ---------
        Subclasses may specify additional arguments to describe
        how data should be fetched (e.g. indices, preprocessing, etc.).

        Changes
        -------
        data_changed
            Observers will be notified on data_changed, once fetching
            is completed and data are available via the :py:meth:`data`
            property.
        """
        if not self.prepared:
            return  # Nothing to do - FIXME[todo]: maybe raise an exception?

        with self.failure_manager():
            LOG.info(f"Datasouce.fetch({kwargs})")
            self._data = self.get_data(**kwargs)
            self.change('data_changed')

    def unfetch(self):
        LOG.info("Datasource.unfetch - data_changed")
        self._data = None
        self.change('data_changed')

    #
    # Description
    #

    @property
    def description(self) -> str:   # FIXME[todo]
        return self.get_description()

    def get_description(self) -> str:   # FIXME[todo]
        """Provide a description of the Datasource or one of its
        elements.

        Attributes
        ----------
        index: int
            In case of an indexed Datasource, provide a description
            of the given element.
        target: bool
            If target values are available (labeled dataset),
            also report that fact, or in case of an indiviual element
            include its label in the description.
        """
        return self._description

    #
    # Utilities
    #

    def load_datapoint_from_file(self, filename: str) -> np.ndarray:
        """Load a single datapoint from a file.
        This method should be implemented by subclasses.

        Arguments
        ---------
        filename: str
            The absolute filename from which the data should be loaded.

        Returns
        ------
        datapoint
            The datapoint loaded from file.
        """
        raise NotImplementedError(f"The datasource {self.__class__.__name__} "
                                  "does not implement a method to load a "
                                  f"datapoint from file '{filename}'")

    def _read_cache(self, cache: str):
        if cache is None or self._appdirs is None:
            return None
        cache_filename = os.path.join(self._appdirs.user_cache_dir, cache)
        LOG.info(f"Trying to load cache file '{cache_filename}'")
        if not os.path.isfile(cache_filename):
            return None
        return pickle.load(open(cache_filename, 'rb'))

    def _write_cache(self, cache: str, data):
        if cache is None or self._appdirs is None:
            return None
        cache_filename = os.path.join(self._appdirs.user_cache_dir, cache)
        LOG.info(f"Writing filenames to {cache_filename}")
        if not os.path.isdir(self._appdirs.user_cache_dir):
            os.makedirs(self._appdirs.user_cache_dir)
        pickle.dump(data, open(cache_filename, 'wb'))


class Imagesource(Datasource):

    def __init__(self, shape: Tuple=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.shape = shape

    def load_datapoint_from_file(self, filename: str) -> np.ndarray:
        """Load a single datapoint, that is an image, from a file.

        Arguments
        ---------
        filename: str
            The absolute image filename. The file may be in any format
            supported by :py:meth:`imread`.

        Returns
        ------
        image
            The image loaded from file.
        """
        return imread(filename)

    def _get_meta(self, data: Data, **kwargs) -> None:
        """Set the image metdata for the :py:class:`data`.
        """
        super()._get_meta(data, **kwargs)
        data.type = data.TYPE_IMAGE
        shape = kwargs.get('shape', self.shape)
        data.add_attribute('shape', shape, batch=shape is None)

    def _get_data(self, data: Data, **kwargs) -> None:
        """Get data from this :py:class:`Datasource`.
        """
        super()._get_data(data, **kwargs)
        if data and not self.shape:
            data.shape = data.data.shape


class Sectioned(Datasource):
    """A :py:class:`Datasource` with multiple sections (like `train`, `val`,
    `test`, etc.). A subclass of :py:class:`Sectioned` may provide a
    set of section labels via the `sections` class parameter.
    """

    def __init_subclass__(cls, sections: set = None, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if sections is not None:
            cls.sections = sections

    def __init__(self, section: str = None, **kwargs) -> None:
        if section not in self.sections:
            raise ValueError(f"Invalid section '{section}'. "
                             f"Should be from {self.sections}.")
        super().__init__(**kwargs)
        self._section = section

    @property
    def section(self):
        return self._section

    @section.setter
    def section(self, section: str):
        self._section = section


class Loop(Datasource):
    """The :py:class:`Loop` class provides a loop logic.

    Notice: the methods of this class are not intended to be
    called directly, but they are engaged via the
    :py:meth:`loop` method of the :py:class:`datasource.Controller`
    class.

    Attributes
    ----------
    _loop_stop_event: threading.Event
        An Event signaling that the loop should stop.
        If not set, this means that the loop is currently running,
        if set, this means that the loop is currently not running (or at
        least supposed to stop running soon).
    _loop_interval: float
        The time in (fractions of a second) between two successive
        fetches when running the loop.
    """

    # An event manages a flag that can be set to true with the set()
    # method and reset to false with the clear() method.

    def __init__(self, loop_interval: float = 0.2, **kwargs) -> None:
        """

        Arguments
        ---------
        """
        super().__init__(**kwargs)
        self._loop_stop_event = threading.Event()
        self._loop_stop_event.set()
        self._loop_interval = loop_interval

    @property
    def looping(self):
        """Check if this datasource is currently looping.
        """
        return not self._loop_stop_event.is_set()

    def loop(self, looping: bool = None):
        """Start or stop looping through the Datasource.
        This will fetch one data point after another.
        This is mainly intended to display live input like
        movies or webcam, but it can also be used for other Datasources.
        """
        if looping is not None and (looping == self.looping):
            return

        if self.looping:
            LOG.info("Stopping datasource loop")
            self.stop_loop()
        else:
            LOG.info("Starting datasource loop")
            self.start_loop()
            self.run_loop()

    def start_loop(self):
        """Start an asynchronous loop cycle. This method will return
        immediately, running the loop cycle in a background thread.
        """
        if self._loop_stop_event.is_set():
            self._loop_stop_event.clear()

    def stop_loop(self):
        """Stop a currently running loop.
        """
        if not self._loop_stop_event.is_set():
            self._loop_stop_event.set()

    @busy("looping")
    def run_loop(self):
        """
        This method is intended to be invoked in its own Thread.
        """
        LOG.info(f"Loop[{self}]: start loop")
        self._run_loop()
        LOG.info(f"Loop[{self}]: end loop")

    def _run_loop(self):
        """Actual implementation of the loop. This method schould
        be overwritten by subclasses for adaptation.
        """

        while not self._loop_stop_event.is_set():
            # Fetch a data item
            last_time = time.time()
            LOG.debug(f"Loop: {self._loop_stop_event.is_set()} "
                      f"at {last_time:.4f}")
            self.fetch()

            # Now wait before fetching the next input
            sleep_time = last_time + self._loop_interval - time.time()
            if sleep_time > 0:
                self._loop_stop_event.wait(timeout=sleep_time)
            else:
                LOG.debug(f"Loop: late for {-sleep_time:.4f}s")


class Snapshot(Datasource):
    """Instances of this class are able to provide a snapshot.  Typical
    examples of :py:class:`Snapshot` datasources are sensors and
    cameras that obtain changing data from the environment.
    Calling the :py:meth:`snapshot` (or :py:meth:`fetch_snapshot`) method
    will provide data reflecting the current state of affairs.

    Notes
    -----

    Subclasses of :py:class:`Snapshot` may overwrite the
    py:class:`_get_snapshot` method to provide a snapshot.
    The standard implementation will just call py:class:`_get_default`.
    """

    def __init__(self, **kwargs) -> None:
        """Instantiate a new :py:class:`Snapshot` object.
        """
        super().__init__(**kwargs)

    def snapshot(self, **kwargs) -> None:
        """Create a snapshot (synchronously).
        """
        return self.get_data(snapshot=True, **kwargs)

    def fetch_snapshot(self, **kwargs) -> None:
        """Create a snapshot.
        """
        self.fetch(snapshot=True, **kwargs)

    #
    # private methods
    #

    def _get_meta(self, data: Data, snapshot: bool = None, **kwargs) -> None:
        if snapshot is not None and not data.datasource_argument:
            data.datasource_argument = 'snapshot'
            data.datasource_value = snapshot
        data.add_attribute('time', batch=True)
        super()._get_meta(data, **kwargs)

    def _get_data(self, data: Data, snapshot: bool = None, **kwargs) -> None:
        """A version of :py:meth:`_get_data` that allows for an
        taking a snapshot.

        Arguments
        ---------
        snapshot: bool
            A flag indicating that a snapshot should be taken.
        """
        if snapshot is not None and data.datasource_argument == 'snapshot':
            self._get_snapshot(data, snapshot, **kwargs)
        super()._get_data(data, **kwargs)

    @abstractmethod
    def _get_snapshot(self, data: Data, snapshot: bool = None,
                      **kwargs) -> None:
        """
        """
        LOG.debug(f"Datasource[%s]._get_snapshot(%s, %r): %s",
                  self, snapshot, kwargs, data)
        data.time = time.time()

    def _get_default(self, data: Data, **kwargs) -> None:
        self._get_snapshot(data, **kwargs)


class Random(Loop):
    """An abstract base class for datasources that allow to fetch
    random datapoints and/or batches. Subclasses of this class should
    implement :py:meth:`_fetch_random()`.
    """

    def __init__(self, random_generator: str = 'random', **kwargs) -> None:
        super().__init__(**kwargs)
        self._random_generator = random_generator

    #
    # Public interface
    #

    def get_random(self, **kwargs) -> None:
        """
        This is equivalent to calling `fetch(random=True)`.
        """
        return self.get_data(random=True, **kwargs)

    def fetch_random(self, **kwargs) -> None:
        """
        This is equivalent to calling `fetch(random=True)`.
        """
        return self.fetch(random=True, **kwargs)

    #
    # Private methods
    #

    def _get_meta(self, data: Data, random: bool = False,
                  seed=None, **kwargs) -> None:
        if random is not False and not data.datasource_argument:
            data.datasource_argument = 'random'
            data.datasource_value = seed or random
            if seed is not None:
                # we have a seed for the random number generator
                if self._random_generator == 'numpy':
                    np.random.seed(seed)
                else:
                    random.seed(seed)
        super()._get_meta(data, **kwargs)

    def _get_data(self, data: Data, random: bool = False,
                  seed=None, **kwargs) -> None:
        """A version of :py:meth:`fetch` that allows for an
        additional argument `random`.

        Arguments
        ---------
        random: bool
            If set, a random element is fetched from this
            :py:class:`Datasource`.
        """
        if random is not False and data.datasource_argument == 'random':
            LOG.debug("Datasource[%s]._get_random(%s, %s)", self, data, kwargs)
            self._get_random(data, **kwargs)
        super()._get_data(data, **kwargs)

    @abstractmethod
    def _get_random(self, data: Data, **kwargs) -> None:
        """This method should be implemented by subclasses that claim
        to be a py:meth:`Random` datasource.
        It should perform whatever is necessary to fetch a random
        element from the dataset.
        """
        pass

    def _get_default(self, data: Data, **kwargs) -> None:
        """The default behaviour of an :py:class:`Random` datasource is to
        get a random element (if not changed by subclasses).
        """
        self._get_random(data, **kwargs)


class Indexed(Random):
    """Instances of this class can be indexed.
    """

    def __getitem__(self, index):
        self.fetch_index(index=index)
        return self.get_data()

    def __len__(self) -> int:
        raise NotImplementedError(f"Subclasses of {Indexed.__name__} "
                                  "should implement 'len', but "
                                  f"{type(self).__name__} doesn't do that.")

    def get_description(self, index=None, **kwargs) -> str:
        description = super().get_description(**kwargs)
        if index is not None:
            description += f", index={index}"
        return description

    def _get_meta(self, data: Data, index: int = None, **kwargs) -> None:
        if index is not None and not data.datasource_argument:
            data.datasource_argument = 'index'
            data.datasource_value = index
        data.add_attribute('index', batch=True)
        super()._get_meta(data, **kwargs)

    def _get_data(self, data: Data, index: int = None, **kwargs):
        """A version of :py:meth:`_get_data` that allows for an
        additional argument `index`.

        Arguments
        ---------
        index: int
            The index of the element in this
            :py:class:`Indexed` datasource.
        """
        if index is not None and data.datasource_argument == 'index':
            LOG.debug(f"Datasource[{self}]._get_index({index},{kwargs}): "
                      f"{data}")
            self._get_index(data, index, **kwargs)
        super()._get_data(data, **kwargs)

    #
    # Data
    #

    @abstractmethod
    def _get_index(self, data: Data, index: int, **kwargs) -> None:
        """This method should be implemented by subclasses that claim
        to be a py:meth:`Indexed` datasource.
        It should perform whatever is necessary to fetch a element with
        the given index from the dataset.
        """
        pass

    def _get_random(self, data: Data, **kwargs) -> None:
        """Get a random element. In a :py:class:`Indexed` datasource
        we can simply choose a random index and fetch that index.
        """
        index = random.randrange(len(self))
        self._get_index(data, index=index, **kwargs)

    #
    # Public interface (convenience functions)
    #

    @property
    def index(self):
        """The index of the currently fetched data item.
        """
        # FIXME[hack]: unprepared datasources should raise an exception
        return (self._data and hasattr(self, '_data') and
                hasattr(self._data, 'index') and self._data.index or 0)

    def fetch_index(self, index: int, **kwargs) -> None:
        """This method should be implemented by subclasses that claim
        to be a py:meth:`Random` datasource.
        It should perform whatever is necessary to fetch a random
        element from the dataset.
        """
        self.fetch(index=index, **kwargs)

    def fetch_next(self, cycle: bool = True, **kwargs) -> None:
        """Fetch the next entry. In a :py:class:`Indexed` datasource
        we can simply increase the index by one.
        """
        current_index = self.index
        next_index = (current_index + 1) if current_index < len(self) else 0
        self.fetch(index=next_index, **kwargs)

    def fetch_prev(self, cycle: bool = True, **kwargs) -> None:
        """Fetch the previous entry. In a :py:class:`Indexed` datasource
        we can simply decrease the index by one.
        """
        current_index = self.index
        next_index = (current_index - 1) if current_index > 0 else len(self)
        self.fetch(index=next_index, **kwargs)

    def fetch_first(self, **kwargs) -> None:
        """Fetch the first entry of this :py:class:`Indexed` datasource.
        This is equivalent to fetching index 0.
        """
        self.fetch(index=0, **kwargs)

    def fetch_last(self, **kwargs) -> None:
        """Fetch the last entry of this :py:class:`Indexed` datasource.
        This is equivalent to fetching the element with index `len(self)-1`.
        """
        self.fetch(index=len(self)-1, **kwargs)


#
# FIXME[old/todo]: things that are not really used (yet)
#
class TODO:
    #
    # FIXME[old]: stuff from the now obsolote "Predefined" class
    # -> probably, this can be removed or realized in other ways ...
    #

    def check_availability(self) -> bool:   # FIXME[todo]
        """Check if this Datasource is available.

        Returns
        -------
        True if the Datasource can be instantiated, False otherwise.
        """
        return False

    def download(self):
        #  (self, file, url, md5sum: str=None, sha1sum: str=None) -> None:
        raise NotImplementedError("Downloading this datasource is "
                                  "not implemented yet.")

    def _install(self):
        pass  # FIXME[todo]
        # download
        # self.download(md5sum=)

        # check
        #
        # unpack
        #


class Labeled(Datasource):
    """A :py:class:`Datasource` that provides labels for its data.

    Datasources that provide labeled data should derive from this class.
    These subclasses should implement the following methods:

    :py:meth:`_prepare_labels` to prepare the use of labels, after which
    the :py:attr:`number_of_labels` property should provide the number
    of labels. If there exists multiple label formats, like textual labels
    or alternate indexes, this can be added by calling
    :py:meth:`add_label_format`.

    :py:meth:`_get_label` and :py:meth:`_get_batch_labels` have to
    be implemented to provide labels for the current data point/batch.

    Attributes
    ----------
    _label_formats: Mapping[str, Union[np.ndarray,list]]
        A mapping of supported container formats. Each format identifier
        is mapped to some lookup table.
    _label_reverse: Mapping[str, Union[np.ndarray,list]]
        A mapping of supported container formats. A format identifier
        is mapped to some reverse lookup table.  Not all reverse
        lookup tables may initially exist, but they are created
        on the fly in :py:meth:`format_labels` the first time they
        are needed.
    """
    _label_formats: dict = None
    _label_reverse: dict = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._label_formats = {}
        self._label_reverse = {}

    def _prepare_labels(self):
        """Actual implementation of :py:meth:`prepare_labels` to be
        overwritten by subclasses.
        """
        pass  # to be implemented by subclasses

    def unprepare_labels(self):
        """Free resources allocated by labels. Should be called
        when labels are no longer needed.
        """
        if self.labels_prepared:
            self._formats = {}
            self.change('labels_changed')

    @property
    def label(self) -> int:
        """Get the (numeric) for the current data point.
        This presupposes, that a current data point has been selected
        before by calling :py:meth:`fetch()`
        """
        return self.get_label()

    def get_label(self, format: str = None):
        """Get the (numeric) label for the current data point.
        This presupposes, that a current data point has been selected
        before by calling :py:meth:`fetch()`
        """
        if not self.labels_prepared:
            raise RuntimeError("Labels have not been prepared yet.")
        if not self.fetched:
            raise RuntimeError("No data has been fetched.")
        label = self._get_label()
        return label if format is None else self.format_label(label, format)

    def _get_label(self):
        """The actual implementation of the :py:meth:`label` property
        to be overwritten by subclasses.

        It can be assumed that a data point has been fetched when this
        method is invoked.
        """
        raise NotImplementedError(f"{self.__class__.__name__} claims to be "
                                  "a 'Labeled' datasource, but it does not "
                                  "implement the '_get_label' method")

    @property
    def batch_labels(self) -> np.ndarray:
        """Get the (numeric) labels for the currently selected batch.
        """
        return self._get_batch_labels()

    def _get_batch_labels(self) -> np.ndarray:
        """The actual implementation of the :py:meth:`batch_labels`
        to be overwritten by subclasses.

        It can be assumed that a batch has been fetched when this
        method is invoked.
        """
        raise NotImplementedError(f"{self.__class__.__name__} claims to be "
                                  "a 'Labeled' datasource, but it does not "
                                  "implement the '_get_batch_labels' method")

    @property
    def label_formats(self):
        """Get a list of label formats supported by this
        :py:class:`Datasource`. Formats from this list can be passed
        as format argument to the :py:meth:`get_label` method.

        Returns
        ------
        formats: List[str]
            A list of str naming the supported label formats.
        """
        return list(self._label_formats.keys())

    def format_labels(self, labels, format: str = None, origin: str = None):
        """Translate labels in a given format.

        Arguments
        ---------
        labels:
            The labels to transfer in another format. Either a single
            (numerical) label or some iterable.
        format: str
            The label format, we want the labels in. If None, the
            internal format will be used.
        origin: str
            The format in which the labels are provided. In None, the
            internal format will be assumed.

        Returns
        ------
        formated_labels:
            The formated labels. Either a single label or some iterable,
            depending how labels were provided.
        """
        if labels is None:
            return None

        # Step 1: convert labels into internal format
        if origin is not None:
            # labels are in some custom (not the internal) format
            # -> we will transform them into the internal format first

            # Step 1a: check if we know the label format
            if origin not in self._label_formats:
                raise ValueError(f"Format {origin} is not supported by "
                                 f"{self.__class__.__name__}. Known formats "
                                 f"are: {self._label_formats.keys()}")

            # Step 1b: check if we have a reverse lookup table
            if origin not in self._label_reverse:
                # if no such table exists yet, create a new one
                table = self._label_formats[origin]
                if isinstance(table, np.ndarray):
                    # FIXME[hack]: assume 0-based labels with no "gaps"
                    reverse_table = np.argsort(table)
                else:
                    reverse_table = {v: i for i, v in enumerate(table)}
                self._label_reverse[origin] = reverse_table
            else:
                reverse_table = self._label_reverse[origin]

            # Step 1c: do the conversion
            if isinstance(labels, int) or isinstance(labels, str):
                # an individual label
                labels = reverse_table[labels]
            elif isinstance(reverse_table, np.ndarray):
                # multiple labels with numpy reverse lookup table
                labels = reverse_table[labels]
            else:
                # multiple labels with another form of reverse lookup table
                labels = [reverse_table[label] for label in labels]

        # Step 2: convert labels into target format
        if format is None:
            return labels  # nothing to do ...

        if format in self._label_formats:
            table = self._label_formats[format]
            if isinstance(labels, int) or isinstance(labels, str):
                # an individual label
                return table[labels]
            elif isinstance(table, np.ndarray):
                # multiple labels with a numpy lookup table
                return table[labels]
            else:
                # multiple labels with another form of lookup table
                return [table[label] for label in labels]
        else:
            raise ValueError(f"Format {format} is not supported by "
                             f"{self.__class__.__name__}. Known formats "
                             f"are: {self._label_formats}")

    def add_label_format(self, format: str, formated_labels) -> None:
        """Provide some texts for the labels of this Labeled Datasource.

        Arguments
        ---------
        format: str
            The name of the format to add.
        formated_labels: list
            A list of formated labels.

        Raises
        ------
        ValueError:
            If the provided texts to not fit the labels.
        """
        if self.number_of_labels != len(formated_labels):
            raise ValueError("Provided wrong number of formated labels: "
                             f"expected {self.number_of_labels}, "
                             f"got {len(formated_labels)}")
        self._label_formats[format] = formated_labels

    def one_hot_for_labels(self, labels, format: str = None,
                           dtype=np.float32) -> np.ndarray:
        """Get the one-hot representation for a given label.

        Arguments
        ---------
        labels: Union[int, Sequence[int]]

        Returns
        ------
        one_hot: np.ndarray
            A one hot vector (1D) in case a single label was provided,
            or 2D matrix containing one hot vectors as rows.
        """
        if format is not None:
            labels = self.format_labels(labels, format)
        if isinstance(labels, int):
            output = np.zeros(self.number_of_labels, dtype=dtype)
            output[label] = 1
        else:
            output = np.zeros((len(labels), self.number_of_labels),
                              dtype=dtype)
            for label in labels:
                output[label] = 1
        return output

    # FIXME[old]:

    def get_description(self, with_label: bool = False, **kwargs) -> str:
        """Provide a description of the Datasource or one of its
        elements.

        Attributes
        ----------
        with_label: bool
            Provide information if labels are available.
        """
        description = super().get_description(**kwargs)
        if with_label:
            if not self.labels_prepared:
                description += " (without labels)"
            else:  # FIXME[hack]: description2 is not used ...
                description2 = f" (with {self.number_of_labels})"
                if self.fetched:
                    label = self._get_label()
                    description += f": {label}"
                    # FIXME[bug]: it should never happen that label is None
                    # - repair and than remove the if statement ...
                    if label is not None:
                        for format in self._label_formats.keys():
                            formated_label = self.format_labels(label, format)
                            description2 += f", {format}: {formated_label}"
        return description

from typing import List, Optional, Union

import pandas as pd  # type: ignore
from typeguard import typechecked

from arkouda import Categorical, Strings
from arkouda.dtypes import bool as akbool
from arkouda.dtypes import float64 as akfloat64
from arkouda.dtypes import int64 as akint64
from arkouda.groupbyclass import GroupBy, unique
from arkouda.infoclass import list_registry
from arkouda.pdarrayclass import pdarray
from arkouda.pdarraycreation import arange, array, ones
from arkouda.pdarraysetops import argsort, in1d
from arkouda.sorting import coargsort
from arkouda.util import convert_if_categorical, generic_concat, get_callback, register


class Index:
    @typechecked
    def __init__(
        self,
        values: Union[List, pdarray, Strings, Categorical, pd.Index, "Index"],
        name: Optional[str] = None,
    ):
        if isinstance(values, Index):
            self.values = values.values
            self.size = values.size
            self.dtype = values.dtype
            self.name = name if name else values.name
        elif isinstance(values, pd.Index):
            self.values = array(values.values)
            self.size = values.size
            self.dtype = self.values.dtype
            self.name = name if name else values.name
        elif isinstance(values, List):
            values = array(values)
            self.values = values
            self.size = self.values.size
            self.dtype = self.values.dtype
            self.name = name
        elif isinstance(values, (pdarray, Strings, Categorical)):
            self.values = values
            self.size = self.values.size
            self.dtype = self.values.dtype
            self.name = name
        else:
            raise TypeError(f"Unable to create Index from type {type(values)}")

    def __getitem__(self, key):
        from arkouda.series import Series

        if isinstance(key, Series):
            key = key.values

        if isinstance(key, int):
            return self.values[key]

        return Index(self.values[key])

    def __repr__(self):
        # Configured to match pandas
        return f"Index({repr(self.index)}, dtype='{self.dtype}')"

    def __len__(self):
        return len(self.index)

    def __eq__(self, v):
        if isinstance(v, Index):
            return self.index == v.index
        return self.index == v

    @property
    def index(self):
        """
        This is maintained to support older code
        """
        return self.values

    @property
    def shape(self):
        return (self.size,)

    @property
    def is_unique(self):
        """
        Property indicating if all values in the index are unique
        Returns
        -------
            bool - True if all values are unique, False otherwise.
        """
        g = GroupBy(self.values)
        key, ct = g.count()
        return (ct == 1).all()

    @staticmethod
    def factory(index):
        t = type(index)
        if isinstance(index, Index):
            return index
        elif t != list and t != tuple:
            return Index(index)
        else:
            return MultiIndex(index)

    def to_pandas(self):
        val = convert_if_categorical(self.values).to_ndarray()
        return pd.Index(data=val, dtype=val.dtype, name=self.name)

    def to_ndarray(self):
        val = convert_if_categorical(self.values)
        return val.to_ndarray()

    def to_list(self):
        return self.to_ndarray().tolist()

    def set_dtype(self, dtype):
        """Change the data type of the index

        Currently only aku.ip_address and ak.array are supported.
        """
        new_idx = dtype(self.values)
        self.values = new_idx
        return self

    def register(self, label):
        register(self.values, f"{label}_key")
        self.name = label
        return 1

    def is_registered(self):
        """
        Return True if the object is contained in the registry

        Returns
        -------
        bool
            Indicates if the object is contained in the registry

        Raises
        ------
        RuntimeError
            Raised if there's a server-side error thrown
        """
        return f"{self.name}_key" in list_registry()

    def to_dict(self, label):
        data = {}
        if label is None:
            label = "idx"
        elif isinstance(label, list):
            label = label[0]
        data[label] = self.index
        return data

    def _check_types(self, other):
        if type(self) is not type(other):
            raise TypeError("Index Types must match")

    def _merge(self, other):
        self._check_types(other)

        callback = get_callback(self.values)
        idx = generic_concat([self.values, other.values], ordered=False)
        return Index(callback(unique(idx)))

    def _merge_all(self, idx_list):
        idx = self.values
        callback = get_callback(idx)

        for other in idx_list:
            self._check_types(other)
            idx = generic_concat([idx, other.values], ordered=False)

        return Index(callback(unique(idx)))

    def _check_aligned(self, other):
        self._check_types(other)
        length = len(self)
        return len(other) == length and (self == other.values).sum() == length

    def argsort(self, ascending=True):
        if not ascending:
            if isinstance(self.values, pdarray) and self.dtype in (akint64, akfloat64):
                i = argsort(-self.values)
            else:
                i = argsort(self.values)[arange(self.size - 1, -1, -1)]
        else:
            i = argsort(self.values)
        return i

    def concat(self, other):
        self._check_types(other)

        idx = generic_concat([self.values, other.values], ordered=True)
        return Index(idx)

    def lookup(self, key):
        if not isinstance(key, pdarray):
            # try to handle single value
            try:
                key = array([key])
            except Exception:
                raise TypeError("Lookup must be on an arkouda array")

        return in1d(self.values, key)

    def to_hdf(
        self,
        prefix_path: str,
        dataset: str = "index",
        mode: str = "truncate",
        file_type: str = "distribute",
    ) -> str:
        """
        Save the Index to HDF5.
        The object can be saved to a collection of files or single file.
        Parameters
        ----------
        prefix_path : str
            Directory and filename prefix that all output files share
        dataset : str
            Name of the dataset to create in files (must not already exist)
        mode : str {'truncate' | 'append'}
            By default, truncate (overwrite) output files, if they exist.
            If 'append', attempt to create new dataset in existing files.
        file_type: str ("single" | "distribute")
            Default: "distribute"
            When set to single, dataset is written to a single file.
            When distribute, dataset is written on a file per locale.
            This is only supported by HDF5 files and will have no impact of Parquet Files.
        Returns
        -------
        string message indicating result of save operation
        Raises
        -------
        RuntimeError
            Raised if a server-side error is thrown saving the pdarray
        Notes
        -----
        - The prefix_path must be visible to the arkouda server and the user must
        have write permission.
        - Output files have names of the form ``<prefix_path>_LOCALE<i>``, where ``<i>``
        ranges from 0 to ``numLocales`` for `file_type='distribute'`. Otherwise,
        the file name will be `prefix_path`.
        - If any of the output files already exist and
        the mode is 'truncate', they will be overwritten. If the mode is 'append'
        and the number of output files is less than the number of locales or a
        dataset with the same name already exists, a ``RuntimeError`` will result.
        - Any file extension can be used.The file I/O does not rely on the extension to
        determine the file format.
        """
        return self.values.to_hdf(prefix_path, dataset=dataset, mode=mode, file_type=file_type)

    def update_hdf(
        self,
        prefix_path: str,
        dataset: str = "array",
        repack: bool = True,
    ):
        """
        Overwrite the dataset with the name provided with this Index object. If
        the dataset does not exist it is added.

        Parameters
        -----------
        prefix_path : str
            Directory and filename prefix that all output files share
        dataset : str
            Name of the dataset to create in files
        repack: bool
            Default: True
            HDF5 does not release memory on delete. When True, the inaccessible
            data (that was overwritten) is removed. When False, the data remains, but is
            inaccessible. Setting to false will yield better performance, but will cause
            file sizes to expand.

        Returns
        --------
        str - success message if successful

        Raises
        -------
        RuntimeError
            Raised if a server-side error is thrown saving the index

        Notes
        ------
        - If file does not contain File_Format attribute to indicate how it was saved,
          the file name is checked for _LOCALE#### to determine if it is distributed.
        - If the dataset provided does not exist, it will be added
        - Because HDF5 deletes do not release memory, this will create a copy of the
          file with the new data
        """
        return self.values.update_hdf(prefix_path, dataset=dataset, repack=repack)

    def to_parquet(
        self,
        prefix_path: str,
        dataset: str = "index",
        mode: str = "truncate",
        compression: Optional[str] = None,
    ):
        """
        Save the Index to Parquet. The result is a collection of files,
        one file per locale of the arkouda server, where each filename starts
        with prefix_path. Each locale saves its chunk of the array to its
        corresponding file.
        Parameters
        ----------
        prefix_path : str
            Directory and filename prefix that all output files share
        dataset : str
            Name of the dataset to create in files (must not already exist)
        mode : str {'truncate' | 'append'}
            By default, truncate (overwrite) output files, if they exist.
            If 'append', attempt to create new dataset in existing files.
        compression : str (Optional)
            (None | "snappy" | "gzip" | "brotli" | "zstd" | "lz4")
            Sets the compression type used with Parquet files
        Returns
        -------
        string message indicating result of save operation
        Raises
        ------
        RuntimeError
            Raised if a server-side error is thrown saving the pdarray
        Notes
        -----
        - The prefix_path must be visible to the arkouda server and the user must
        have write permission.
        - Output files have names of the form ``<prefix_path>_LOCALE<i>``, where ``<i>``
        ranges from 0 to ``numLocales`` for `file_type='distribute'`.
        - 'append' write mode is supported, but is not efficient.
        - If any of the output files already exist and
        the mode is 'truncate', they will be overwritten. If the mode is 'append'
        and the number of output files is less than the number of locales or a
        dataset with the same name already exists, a ``RuntimeError`` will result.
        - Any file extension can be used.The file I/O does not rely on the extension to
        determine the file format.
        """
        return self.values.to_parquet(prefix_path, dataset=dataset, mode=mode, compression=compression)

    @typechecked
    def to_csv(
        self,
        prefix_path: str,
        dataset: str = "index",
        col_delim: str = ",",
        overwrite: bool = False,
    ):
        """
        Write Index to CSV file(s). File will contain a single column with the pdarray data.
        All CSV Files written by Arkouda include a header denoting data types of the columns.

        Parameters
        -----------
        prefix_path: str
            The filename prefix to be used for saving files. Files will have _LOCALE#### appended
            when they are written to disk.
        dataset: str
            Column name to save the pdarray under. Defaults to "array".
        col_delim: str
            Defaults to ",". Value to be used to separate columns within the file.
            Please be sure that the value used DOES NOT appear in your dataset.
        overwrite: bool
            Defaults to False. If True, any existing files matching your provided prefix_path will
            be overwritten. If False, an error will be returned if existing files are found.

        Returns
        --------
        str reponse message

        Raises
        ------
        ValueError
            Raised if all datasets are not present in all parquet files or if one or
            more of the specified files do not exist
        RuntimeError
            Raised if one or more of the specified files cannot be opened.
            If `allow_errors` is true this may be raised if no values are returned
            from the server.
        TypeError
            Raised if we receive an unknown arkouda_type returned from the server

        Notes
        ------
        - CSV format is not currently supported by load/load_all operations
        - The column delimiter is expected to be the same for column names and data
        - Be sure that column delimiters are not found within your data.
        - All CSV files must delimit rows using newline (`\n`) at this time.
        """
        return self.values.to_csv(prefix_path, dataset=dataset, col_delim=col_delim, overwrite=overwrite)

    def save(
        self,
        prefix_path: str,
        dataset: str = "index",
        mode: str = "truncate",
        compression: Optional[str] = None,
        file_format: str = "HDF5",
        file_type: str = "distribute",
    ) -> str:
        """
        DEPRECATED
        Save the index to HDF5 or Parquet. The result is a collection of files,
        one file per locale of the arkouda server, where each filename starts
        with prefix_path. Each locale saves its chunk of the array to its
        corresponding file.
        Parameters
        ----------
        prefix_path : str
            Directory and filename prefix that all output files share
        dataset : str
            Name of the dataset to create in files (must not already exist)
        mode : str {'truncate' | 'append'}
            By default, truncate (overwrite) output files, if they exist.
            If 'append', attempt to create new dataset in existing files.
        compression : str (Optional)
            (None | "snappy" | "gzip" | "brotli" | "zstd" | "lz4")
            Sets the compression type used with Parquet files
        file_format : str {'HDF5', 'Parquet'}
            By default, saved files will be written to the HDF5 file format. If
            'Parquet', the files will be written to the Parquet file format. This
            is case insensitive.
        file_type: str ("single" | "distribute")
            Default: "distribute"
            When set to single, dataset is written to a single file.
            When distribute, dataset is written on a file per locale.
            This is only supported by HDF5 files and will have no impact of Parquet Files.
        Returns
        -------
        string message indicating result of save operation
        Raises
        ------
        RuntimeError
            Raised if a server-side error is thrown saving the pdarray
        ValueError
            Raised if there is an error in parsing the prefix path pointing to
            file write location or if the mode parameter is neither truncate
            nor append
        TypeError
            Raised if any one of the prefix_path, dataset, or mode parameters
            is not a string
        See Also
        --------
        save_all, load, read, to_parquet, to_hdf
        Notes
        -----
        The prefix_path must be visible to the arkouda server and the user must
        have write permission.
        Output files have names of the form ``<prefix_path>_LOCALE<i>``, where ``<i>``
        ranges from 0 to ``numLocales``. If any of the output files already exist and
        the mode is 'truncate', they will be overwritten. If the mode is 'append'
        and the number of output files is less than the number of locales or a
        dataset with the same name already exists, a ``RuntimeError`` will result.
        Previously all files saved in Parquet format were saved with a ``.parquet`` file extension.
        This will require you to use load as if you saved the file with the extension. Try this if
        an older file is not being found.
        Any file extension can be used. The file I/O does not rely on the extension to determine the
        file format.
        """
        from warnings import warn

        warn(
            "ak.Index.save has been deprecated. Please use ak.Index.to_parquet or ak.Index.to_hdf",
            DeprecationWarning,
        )
        if mode.lower() not in ["append", "truncate"]:
            raise ValueError("Allowed modes are 'truncate' and 'append'")

        if file_format.lower() == "hdf5":
            return self.to_hdf(prefix_path, dataset=dataset, mode=mode, file_type=file_type)
        elif file_format.lower() == "parquet":
            return self.to_parquet(prefix_path, dataset=dataset, mode=mode, compression=compression)
        else:
            raise ValueError("Valid file types are HDF5 or Parquet")


class MultiIndex(Index):
    def __init__(self, values):
        if not (isinstance(values, list) or isinstance(values, tuple)):
            raise TypeError("MultiIndex should be an iterable")
        self.values = values
        first = True
        for col in self.values:
            if first:
                # we are implicitly assuming values contains arkouda types and not python lists
                # because we are using obj.size/obj.dtype instead of len(obj)/type(obj)
                # this should be made explict using typechecking
                self.size = col.size
                first = False
            else:
                if col.size != self.size:
                    raise ValueError("All columns in MultiIndex must have same length")
        self.levels = len(self.values)

    def __getitem__(self, key):
        from arkouda.series import Series

        if isinstance(key, Series):
            key = key.values
        return MultiIndex([i[key] for i in self.index])

    def __repr__(self):
        return f"MultiIndex({repr(self.index)})"

    def __len__(self):
        return len(self.index[0])

    def __eq__(self, v):
        if not isinstance(v, (list, tuple, MultiIndex)):
            raise TypeError("Cannot compare MultiIndex to a scalar")
        retval = ones(len(self), dtype=akbool)
        if isinstance(v, MultiIndex):
            v = v.index
        for a, b in zip(self.index, v):
            retval &= a == b

        return retval

    @property
    def index(self):
        return self.values

    def to_pandas(self):
        idx = [convert_if_categorical(i) for i in self.index]
        mi = [i.to_ndarray() for i in idx]
        return pd.Series(index=mi, dtype="float64").index

    def set_dtype(self, dtype):
        """Change the data type of the index

        Currently only aku.ip_address and ak.array are supported.
        """
        new_idx = [dtype(i) for i in self.index]
        self.index = new_idx
        return self

    def register(self, label):
        for i, arr in enumerate(self.index):
            register(arr, f"{label}_key_{i}")
        return len(self.index)

    def to_dict(self, labels):
        data = {}
        if labels is None:
            labels = [f"idx_{i}" for i in range(len(self.index))]
        for i, value in enumerate(self.index):
            data[labels[i]] = value
        return data

    def _merge(self, other):
        self._check_types(other)
        idx = [generic_concat([ix1, ix2], ordered=False) for ix1, ix2 in zip(self.index, other.index)]
        return MultiIndex(GroupBy(idx).unique_keys)

    def _merge_all(self, array):
        idx = self.index

        for other in array:
            self._check_types(other)
            idx = [generic_concat([ix1, ix2], ordered=False) for ix1, ix2 in zip(idx, other.index)]

        return MultiIndex(GroupBy(idx).unique_keys)

    def argsort(self, ascending=True):
        i = coargsort(self.index)
        if not ascending:
            i = i[arange(self.size - 1, -1, -1)]
        return i

    def concat(self, other):
        self._check_types(other)
        idx = [generic_concat([ix1, ix2], ordered=True) for ix1, ix2 in zip(self.index, other.index)]
        return MultiIndex(idx)

    def lookup(self, key):
        if not isinstance(key, list) and not isinstance(key, tuple):
            raise TypeError("MultiIndex lookup failure")
        # if individual vals convert to pdarrays
        if not isinstance(key[0], pdarray):
            key = [array([x]) for x in key]
        return in1d(self.index, key)

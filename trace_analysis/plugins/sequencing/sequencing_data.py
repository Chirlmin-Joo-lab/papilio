import numpy as np
from pathlib import Path
import h5py
import re
import pandas as pd
import netCDF4
import h5netcdf
import tqdm
from contextlib import ExitStack
import xarray as xr

from trace_analysis.plugins.sequencing.plotting import plot_cluster_locations_per_tile

# Update class with new sam analysis function below
class SequencingData:

    reagent_kit_info = {'v2':       {'number_of_tiles': 14, 'number_of_surfaces': 2},
                        'v2_micro': {'number_of_tiles':  4, 'number_of_surfaces': 2},
                        'v2_nano':  {'number_of_tiles':  2, 'number_of_surfaces': 1},
                        'v3':       {'number_of_tiles': 19, 'number_of_surfaces': 2}}

    # @classmethod
    # def load(cls):
    #     cls()

    def __init__(self, file_path=None, dataset=None, name='', reagent_kit='v3', file_kwargs={}):
        if file_path is not None:
            file_path = Path(file_path)
            if file_path.suffix == '.nc':
                # with xr.open_dataset(file_path.with_suffix('.nc'), engine='h5netcdf') as dataset:
                #     self.dataset = dataset.load().set_index({'sequence': ('tile','x','y')})
                self.dataset = xr.open_dataset(file_path.with_suffix('.nc'), engine='netcdf4')#, chunks=10000)
                self.dataset = self.dataset.set_index({'sequence': ('tile', 'x', 'y')})
            else:
                data = pd.read_csv(file_path, delimiter='\t')
                data.columns = data.columns.str.lower()
                data = data.set_index(['tile', 'x', 'y'])
                data = data.drop_duplicates() # TODO: It would be better to do this when converting the sam file.
                data.index.name = 'sequence' # Do this after drop_duplicates!
                self.dataset = xr.Dataset(data) #.reset_index('sequence', drop=True)

                if name == '':
                    name = Path(file_path).name

        elif dataset is not None:
            self.dataset = dataset
        else:
            raise ValueError('Either file_path or data should be given')

        self.name = name

        self.reagent_kit = reagent_kit
        self.reagent_kit_info = SequencingData.reagent_kit_info[reagent_kit]

        self._tiles = None


    def __getattr__(self, item):
        #try:
        print('seqdata=' + item)
        if 'dataset' in self.__dict__.keys() and hasattr(self.dataset, item):
            return getattr(self.dataset, item)
        #except AttributeError:
        #    super().__getattribute__(item)
        else:
            raise AttributeError
            # super(SequencingData, self).__getattribute__(item)

        # try:
        #     return getattr(self.dataset, item)
        # except AttributeError:
        #     super().__getattribute__(item)

    def __getitem__(self, item):
        return SequencingData(dataset=self.dataset.sel(sequence=item))

    def __repr__(self):
        return (f'{self.__class__.__name__}({self.name})')

    @property
    def coordinates(self):
        return self.dataset[['x','y']].to_array(dim='dimension', name='coordinates').transpose('sequence',...)
            # xr.DataArray(self.data[['x','y']], dims=['sequence', 'dimension'], name='coordinates')\
            # .reset_index('sequence', drop=True)

    @property
    def tile_numbers(self):
        return np.unique(self.dataset.tile)

    @property
    def tiles(self):
        if not self._tiles:
            # Perhaps more elegant if this returns SequencingData objects [25-10-2021 IS]
            self._tiles = [Tile(tile, tile_coordinates) for tile, tile_coordinates in self.coordinates.groupby('tile')]
        return self._tiles

    def sel(self, *args, **kwargs):
        return SequencingData(dataset=self.dataset.sel(*args, **kwargs))

    def plot_cluster_locations_per_tile(self, save_filepath=None):
        plot_cluster_locations_per_tile(self.dataset[['x','y']], **self.reagent_kit_info, save_filepath=save_filepath)

    def save(self, filepath):
        self.dataset.reset_index('sequence').to_netcdf(filepath, engine='h5netcdf', mode='w')

class Tile:
    def __init__(self, number, coordinates):
        self.name = str(number)
        self.number = number
        self.coordinates = coordinates

    def __repr__(self):
        return (f'{self.__class__.__name__}({self.name})')



def read_sam(sam_filepath, add_aligned_sequence=False, extract_sequence_subset=False, read_name='read1'):
    sam_filepath = Path(sam_filepath)

    # Check number of header lines:
    with Path(sam_filepath).open('r') as file:
        number_of_header_lines = 0
        while file.readline()[0] == '@':
            number_of_header_lines += 1

    df = pd.read_csv(sam_filepath,
                     delimiter='\t', skiprows=number_of_header_lines, usecols=range(11), header=None,
                     names=['sequence_identifier', 'sam_flag', 'reference_name', 'position', 'mapping_quality', 'cigar_string',
                            'mate_reference_name', 'mate_position', 'template_length', name+'_sequence', name+'_quality'])
    df = df.drop_duplicates(subset='sequence_identifier', keep='first', ignore_index=False)
    df.index.name = 'sequence'
    df_split = df['sequence_identifier'].str.split(':', expand=True)
    df_split.columns = ['instrument', 'run', 'flowcell', 'lane', 'tile', 'x', 'y']
    df_split = df_split.astype({'run': int, 'lane': int, 'tile': int, 'x': int, 'y': int})
    df_joined = df_split.join(df.iloc[:, 1:])

    if add_aligned_sequence:
        df_joined[[read_name+'_sequence_aligned', read_name+'_quality_aligned']] = \
            df_joined.apply(get_aligned_sequence_from_row, axis=1, result_type='expand', name=name)

    if extract_sequence_subset:
        df_joined['sequence_subset'] = extract_positions(df_joined[read_name+'_sequence_aligned'],
                                                         extract_sequence_subset)
        df_joined['quality_subset'] = extract_positions(df_joined[read_name+'_quality_aligned'],
                                                        extract_sequence_subset)

    return df_joined


def read_sam_header(sam_filepath):
    header_dict = {'HD': [], 'SQ': [], 'RG': [], 'PG':[], 'CO':[]}
    with Path(sam_filepath).open('r') as file:
        number_of_header_lines = 0
        # read_line = file.readline().split('\t')
        while (read_line := file.readline().rstrip('\n').split('\t'))[0][0] == '@':
        # while read_line[0][0] == '@':
            line_data = {item.split(':')[0]: item.split(':')[1] for item in read_line[1:]}
            header_dict[read_line[0][1:]].append(line_data)
            # read_line = file.readline().split('\t')

            number_of_header_lines += 1

    return number_of_header_lines, header_dict

def parse_sam(sam_filepath, read_name='read1', remove_duplicates=True, add_aligned_sequence=False, extract_sequence_subset=False,
              chunksize=10000, write_csv=False, write_nc=True, write_filepath=None):
    sam_filepath = Path(sam_filepath)

    # Check number of header lines:
    number_of_header_lines, header_dict = read_sam_header(sam_filepath)

    name_dict = {'*': 0, '=': 1}
    name_dict.update({SQ_dict['SN']:i+2 for i, SQ_dict in enumerate(header_dict['SQ'])})

    with ExitStack() as stack:

        with pd.read_csv(sam_filepath,
                         delimiter='\t', skiprows=number_of_header_lines, usecols=range(11), header=None,
                         names=['sequence_identifier', 'sam_flag', 'reference_name', 'position', 'mapping_quality',
                                'cigar_string', 'mate_reference_name', 'mate_position', 'template_length',
                                read_name + '_sequence', read_name + '_quality'],
                         chunksize=chunksize) as reader:

            for i, chunk in tqdm.tqdm(enumerate(reader)):
                df_chunk = chunk
                df_chunk.index.name = 'sequence'
                if remove_duplicates:
                    df_chunk = df_chunk[df_chunk.sam_flag//2048 == 0]
                df_split = df_chunk['sequence_identifier'].str.split(':', expand=True)
                df_split.columns = ['instrument', 'run', 'flowcell', 'lane', 'tile', 'x', 'y']
                df_split = df_split.astype({'run': int, 'lane': int, 'tile': int, 'x': int, 'y': int})
                df = df_split.join(df_chunk.iloc[:, 1:])

                if add_aligned_sequence:
                    df[[read_name+'_sequence_aligned', read_name+'_quality_aligned']] = \
                        df.apply(get_aligned_sequence_from_row, axis=1, result_type='expand', read_name=read_name)

                if extract_sequence_subset:
                    df['sequence_subset'] = extract_positions(df[read_name+'_sequence_aligned'], extract_sequence_subset)
                    df['quality_subset'] = extract_positions(df[read_name+'_quality_aligned'], extract_sequence_subset)

                if write_filepath is None:
                    write_filepath = sam_filepath.with_suffix('')

                if write_csv:
                    if i == 0:
                        csv_filepath = write_filepath.with_suffix('.csv')
                        df.to_csv(csv_filepath, header=True, mode='w')
                    else:
                        df.to_csv(csv_filepath, header=False, mode='a')

                if write_nc:
                    if i == 0:
                        nc_filepath = write_filepath.with_suffix('.nc')
                        # with netCDF4.Dataset(nc_filepath, 'w'):
                        #     nc_file.createDimension('sequence', None)

                        nc_file = stack.enter_context(netCDF4.Dataset(nc_filepath, 'w'))
                        nc_file.createDimension('sequence', None)
                        for name, datatype in df.dtypes.items():
                            if name in ['instrument','run','flowcell']:
                                setattr(nc_file, name, df[name][0])
                            elif name in ['reference_name', 'mate_reference_name']:
                                # nc_file.createVariable(name, np.uint8, ('sequence',))
                                # nc_file[name].enum_dict = name_dict
                                size = np.array(list(name_dict.keys())).astype('S').itemsize
                                create_string_variable_in_nc_file(nc_file, name, dimensions=('sequence',), size=size)
                            elif (read_name+'_sequence') in name or (read_name+'_quality') in name:
                                size = len(df[name][0])
                                create_string_variable_in_nc_file(nc_file, name, dimensions=('sequence',), size=size)
                            elif name in ['cigar_string']:
                            # if datatype == np.dtype('O'):
                                # nc_file.createDimension(name + '_size', None)
                                # nc_file.createVariable(name, 'S1', ('sequence', name + '_size'), chunksizes=(10000, 1))
                                # nc_file[name]._Encoding = 'utf-8'
                                create_string_variable_in_nc_file(nc_file, name, dimensions=('sequence',), chunksizes=(10000, 10))
                            else:
                                nc_file.createVariable(name, datatype, ('sequence', ))

                    old_size = nc_file.dimensions['sequence'].size
                    for name, datatype in df.dtypes.items():
                        # print(name)
                        if name in ['instrument', 'run', 'flowcell']:
                            continue
                        elif datatype == np.dtype('O'):
                            size = np.max([2, nc_file.dimensions[name+'_size'].size, df[name].str.len().max()])
                            nc_file[name][old_size:] = df[name].values.astype(f'S{size}')
                        else:
                            nc_file[name][old_size:] = df[name].values


            # Use this if xarray should open the file with standard datatype "|S" instead of "object"
            # for name, datatype in df.dtypes.items():
            #     print(name)
            #     if datatype == np.dtype('O'):
            #         delattr(nc_file[name], '_Encoding')


                    #
                    #     nc_file['cigar_string'][:] = df[0:200].cigar_string.astype('S').values
                    #     # delattr(nc_file['cigar_string'], '_Encoding')
                    #     nc_file.close()
                    #
                    #     test = xr.load_dataset(write_filepath.with_suffix('.nc'))
                    #
                    #
                    #     nc_file = stack.enter_context(h5netcdf.File(nc_filepath, 'a'))
                    #     nc_file.dimensions = {'sequence': None}
                    #     for name, datatype in df.dtypes.items():
                    #         if datatype == np.dtype('O'):
                    #             # datatype = h5py.string_dtype(encoding='utf-8')
                    #             datatype = 'S10'
                    #         else:
                    #             nc_file.create_variable(name, ('sequence',), data=None, dtype=datatype, chunks=(chunksize,))
                    # old_size = nc_file.dimensions['sequence'].size
                    # new_size = old_size + len(df)
                    # nc_file.resize_dimension('sequence', new_size)
                    # added_data_slice = slice(old_size, new_size)
                    # for name in df.columns:
                    #     nc_file[name][added_data_slice] = df[name].values

    #
    # encoding = {key: {'dtype': '|S'} for key in ds.keys() if ds[key].dtype == 'object'}
    #
    # keys = ['instrument', 'run', 'flowcell', 'lane', 'tile', 'x', 'y', 'sam_flag', 'contig_name', 'first_base_position', 'mapping_quality', 'cigar_string', 'mate_name', 'mate_position', 'template_length', 'read_sequence', 'read_quality', 'read_sequence_aligned', 'read_quality_aligned', 'sequence_subset', 'quality_subset', 'index1_sequence', 'index1_quality']
    # with xr.open_dataset(
    #         r'N:\tnw\BN\CMJ\Shared\Ivo\PhD_data\20220607 - Sequencer (MiSeq)\Analysis\sequencing_data.nc') as ds:
    #     keys = list(ds.keys())
    # for key in keys:
    #     print(key)
    #     with xr.open_dataset(r'N:\tnw\BN\CMJ\Shared\Ivo\PhD_data\20220607 - Sequencer (MiSeq)\Analysis\sequencing_data.nc') as ds:
    #         da = ds[key].load()
    #         if da.dtype == 'object':
    #             encoding = {key: {'dtype': '|S'}}
    #         else:
    #             encoding = {}
    #         da.to_netcdf(r'N:\tnw\BN\CMJ\Shared\Ivo\PhD_data\20220607 - Sequencer (MiSeq)\Analysis\sequencing_data_S.nc', engine='h5netcdf', mode='a', encoding=encoding)


# for key in ds.keys():
#     if ds[key].dtype == 'object':
#         print(key)


def fastq_data(fastq_filepath, read_name):
    tile_list = []
    x_list = []
    y_list = []
    sequence = []
    quality = []
    expr = re.compile('[:@ \n]')
    with Path(fastq_filepath).open('r') as fq_file:
        for line_index, line in enumerate(tqdm.tqdm(fq_file)):
            if line_index % 4 == 0:
                name = line.strip()
                instrument, run, flowcell, lane, tile, x, y = expr.split(name)[1:8]
                # sequence_index = numbered_index.loc[dict(sequence=(int(tile), int(x), int(y)))].item()
                tile_list.append(int(tile))
                x_list.append(int(x))
                y_list.append(int(y))

            if line_index % 4 == 1:
                sequence.append(line.strip())
            if line_index % 4 == 3:
                quality.append(line.strip())
    ds = xr.Dataset({read_name+'_sequence': ('sequence', sequence), read_name+'_quality': ('sequence', quality)},
                      coords={'tile': ('sequence', tile_list), 'x': ('sequence', x_list), 'y': ('sequence', y_list)})
    return ds


def fastq_generator(fastq_filepath):
    expr = re.compile('[:@ \n]')
    with Path(fastq_filepath).open('r') as fq_file:
        for line_index, line in enumerate(fq_file):
            if line_index % 4 == 0:
                name = line.strip()
                instrument, run, flowcell, lane, tile, x, y = expr.split(name)[1:8]
                # sequence_index = numbered_index.loc[dict(sequence=(int(tile), int(x), int(y)))].item()
                tile = int(tile)
                x = int(x)
                y = int(y)

            if line_index % 4 == 1:
                sequence = line.strip()
            if line_index % 4 == 3:
                quality = line.strip()
                # yield instrument_name, run_id, flowcell_id, lane, tile, x, y, sequence, quality
                yield {'instrument': instrument, 'run': run, 'flowcell': flowcell, 'lane': lane,
                       'tile': tile, 'x': x, 'y': y, 'sequence': sequence, 'quality': quality}


# def add_sequence_data_to_dataset(nc_filepath, fastq_filepath, name):
#     with xr.open_dataset(nc_filepath, engine='h5netcdf') as ds:
#         sequence_multiindex = ds[['tile', 'x', 'y']].load().set_index({'sequence':('tile','x','y')})#.indexes['sequence']
#
#     ds = fastq_data(fastq_filepath)
#     ds = ds.rename_vars({'read_sequence':f'{name}_sequence', 'read_quality': f'{name}_quality'})
#     ds = ds.set_index({'sequence': ('tile','x','y')})
#     ds, = xr.align(ds, indexes=sequence_multiindex.indexes, copy=False)
#     ds.reset_index('sequence',drop=True)[[f'{name}_sequence', f'{name}_quality']].to_netcdf(nc_filepath, mode='a', engine='h5netcdf')


def create_string_variable_in_nc_file(nc_file, variable_name, fill_value=None, size=None, **kwargs):
    kwargs['dimensions'] += (variable_name + '_size',)
    # if not 'chunksizes' in kwargs.keys():
    #     kwargs['chunksizes'] = (10000, 1)
    nc_file.createDimension(variable_name + '_size', size)
    nc_file.createVariable(variable_name, 'S1', **kwargs)
    nc_file[variable_name]._Encoding = 'utf-8'
    if fill_value is not None:
        if size is None:
            dtype_size = 2
            size = 1
        else:
            dtype_size = np.max([size,2])
        nc_file[variable_name][:] = np.repeat(fill_value*size, nc_file.dimensions[kwargs['dimensions'][0]].size).astype(f'S{dtype_size}')



def add_sequence_data_to_dataset(nc_filepath, fastq_filepath, read_name):
    with netCDF4.Dataset(nc_filepath, 'a') as nc_file:
        for i, sequence_data in tqdm.tqdm(enumerate(fastq_generator(fastq_filepath))):
            if i == 0:
                size = len(sequence_data['sequence'])
                sequence_variable_name = read_name + '_sequence'
                create_string_variable_in_nc_file(nc_file, sequence_variable_name, fill_value='-',
                                                  dimensions=('sequence',), size=size)

                quality_variable_name = read_name + '_quality'
                create_string_variable_in_nc_file(nc_file, quality_variable_name, fill_value=' ',
                                                  dimensions=('sequence',), size=size)

            if (nc_file['tile'][i] == sequence_data['tile']) & \
                    (nc_file['x'][i] == sequence_data['x']) & \
                    (nc_file['y'][i] == sequence_data['y']):
                nc_file[sequence_variable_name][i] = np.array(sequence_data['sequence']).astype('S')
                nc_file[quality_variable_name][i] = np.array(sequence_data['quality']).astype('S')
            else:
                raise ValueError()
#
#
# import xarray as xr
# from tqdm import tqdm
# nc_filepath = sam_filepath.with_suffix('.nc')
# with xr.open_dataset(nc_filepath, engine='h5netcdf') as ds:
#     sequence_multiindex = ds[['tile_number','x','y']].set_index({'sequence':('tile_number','x','y')}).indexes['sequence']
# numbered_index = xr.DataArray(np.arange(len(sequence_multiindex)), dims=('sequence',), coords={'sequence': sequence_multiindex})
# #
# # reference_array = ds[['tile','x','y']].to_array().T
# #
# # index1_sequence = xr.DataArray(np.empty(len(ds.sequence), dtype=str), dims=('sequence',), coords={'sequence': ds.sequence})
# # index1_quality = xr.DataArray(np.empty(len(ds.sequence), dtype=str), dims=('sequence',), coords={'sequence': ds.sequence})
# fastq_filepath = r'N:\tnw\BN\CMJ\Shared\Ivo\PhD_data\20211011 - Sequencer (MiSeq)\Analysis\Index1.fastq'
# with h5netcdf.File(nc_filepath, 'a') as nc_file:
#     if not 'index1_sequence' in nc_file:
#         nc_file.create_variable('index1_sequence', ('sequence',),  h5py.string_dtype(encoding='utf-8'))
#     if not 'index1_quality' in nc_file:
#         nc_file.create_variable('index1_quality', ('sequence',),  h5py.string_dtype(encoding='utf-8'))
#     sequence_index = 0
#     with Path(fastq_filepath).open('r') as fq_file:
#         for line_index, line in enumerate(tqdm(fq_file)):
#             if line_index % 4 == 0:
#                 name = line.strip()
#                 instrument_name, run_id, flowcell_id, lane, tile, x, y = re.split('[:@ \n]', name)[1:8]
#                 #sequence_index = numbered_index.loc[dict(sequence=(int(tile), int(x), int(y)))].item()
#
#             if line_index % 4 == 1:
#                 nc_file['index1_sequence'][sequence_index] = line.strip()
#             if line_index % 4 == 3:
#                 nc_file['index1_quality'][sequence_index] = line.strip()
#                 sequence_index += 1





        #index1_sequence.loc[dict(sequence=(int(tile), int(x), int(y)))] = fq_file.readline().strip()
        #fq_file.readline()
        #index1_quality.loc[dict(sequence=(int(tile), int(x), int(y)))] = fq_file.readline().strip()

def get_aligned_sequence(read_sequence, read_quality, cigar_string, position, reference_range=None):
    if reference_range is None:
        reference_range = (0, len(read_sequence))
    output_length = reference_range[1]-reference_range[0]

    if cigar_string == '*':
        return ('-'*output_length,' '*output_length)

    # cigar_string.split('(?<=M|I|D|N|S|H|P|=|X)')
    # split_cigar_string = re.findall(r'[0-9]*[MIDNSHP=X]', cigar_string)
    cigar_string_split = [(int(s[:-1]), s[-1]) for s in re.findall(r'[0-9]*[MIDNSHP=X]', cigar_string)]
    read_index = 0 # in read_sequence
    aligned_sequence = ''
    aligned_quality = ''

    if cigar_string_split[0][1] == 'S':
        cigar_string_split.pop(0)

    aligned_sequence += '-'* (position - 1)
    aligned_quality += ' ' * (position - 1)
    read_index = position - 1

    for length, code in cigar_string_split:
        if code in ['M','=','X']:
            aligned_sequence += read_sequence[read_index:read_index+length]
            aligned_quality += read_quality[read_index:read_index+length]
            read_index += length
        elif code == 'I':
            read_index += length
        elif code == 'S':
            aligned_sequence += '-'*length
            aligned_quality += ' ' * length
            read_index += length
        elif code in ['D','N']:
            aligned_sequence += '-' * length
            aligned_quality += '-' * length

    length_difference = len(aligned_sequence) - output_length
    if length_difference > 0:
        aligned_sequence = aligned_sequence[:output_length]
        aligned_quality = aligned_quality[:output_length]
    elif length_difference < 0:
        aligned_sequence += (-length_difference) * '-'
        aligned_quality += (-length_difference) * ' '

    return aligned_sequence, aligned_quality

def get_aligned_sequence_from_row(df_row, read_name, reference_range=None):
    sequence = df_row[read_name+'_sequence']
    quality = df_row[read_name+'_quality']
    cigar_string = df_row['cigar_string']
    position = df_row['position']
    return get_aligned_sequence(sequence, quality, cigar_string, position, reference_range)

########### Code to dynamically get aligned bases froj
# def get_aligned_position(index, cigar_string, first_base_position):
#     if cigar_string == '*':
#         return -1
#
#     # cigar_string.split('(?<=M|I|D|N|S|H|P|=|X)')
#     # split_cigar_string = re.findall(r'[0-9]*[MIDNSHP=X]', cigar_string)
#     cigar_string_split = [(int(s[:-1]), s[-1]) for s in re.findall(r'[0-9]*[MIDNSHP=X]', cigar_string)]
#     query_index = 0 # in read_sequence
#     reference_index = first_base_position-1
#     for length, code in cigar_string_split:
#         if code in ['M','I','S','=','X']:
#             query_index += length
#         if code in ['M','D','N','=','X']:
#             reference_index += length
#         #print(f'Reference index: {reference_index}')
#         #print(f'Query index: {query_index}')
#         if reference_index > index:
#             return query_index-reference_index+index
#     return -1
#
# def get_aligned_position_from_row(df_row, index):
#     cigar_string = df_row['cigar_string']
#     first_base_position = df_row['first_base_position']
#     return get_aligned_position(index, cigar_string, first_base_position)
#
#     a = np.array(re.findall(r'[0-9]*(?=[MIS=X])', cigar_string)).astype(int).cumsum()
#     b = np.array([first_base_position-1]+re.findall(r'[0-9]*(?=[MDN=X])', cigar_string)).astype(int).cumsum()
#     return aligned_sequence, aligned_quality


def extract_positions(series, indices):
    for i, index in enumerate(indices):
        if i == 0:
            combined = series.str.get(index)
        else:
            combined += series.str.get(index)
    return combined


def make_sequencing_dataset(file_path, index1_file_path=None, remove_duplicates=True, add_aligned_sequence=True,
                            extract_sequence_subset=False, chunksize=10000):

    file_path = Path(file_path)

    nc_file_path = file_path.with_name('sequencing_data.nc')
    if file_path.suffix == '.sam':
        parse_sam(file_path, remove_duplicates=remove_duplicates, add_aligned_sequence=add_aligned_sequence,
                  extract_sequence_subset=extract_sequence_subset, chunksize=chunksize, write_csv=False, write_nc=True,
                  write_filepath=nc_file_path)
    else:
        raise ValueError('Wrong file type')

    if index1_file_path is not None:
        index1_file_path = Path(index1_file_path)
        if index1_file_path.suffix == '.fastq':
            add_sequence_data_to_dataset(nc_file_path, index1_file_path, 'index1')
        else:
            raise ValueError('Wrong file type for index1')

    return nc_file_path



if __name__ == '__main__':
    file_path = r'J:\Ivo\20211011 - Sequencer (MiSeq)\Analysis\sequencing_data_MapSeq.csv'
    seqdata = SequencingData(file_path=file_path)
    seqdata.plot_cluster_locations_per_tile(save_filepath=r'J:\Ivo\20211011 - Sequencer (MiSeq)\Analysis\Mapping_seqquences_per_tile.png')

    file_path = r'J:\Ivo\20211011 - Sequencer (MiSeq)\Analysis\sequencing_data_HJ_general.csv'
    seqdata_HJ = SequencingData(file_path=file_path)



    # New analysis
    sam_filepath = Path(r'N:\tnw\BN\CMJ\Shared\Ivo\PhD_data\20211011 - Sequencer (MiSeq)\Analysis\Alignment.sam')
    # sequencing_data = read_sam(sam_filepath)

    extract_sequence_subset = [30, 31, 56, 57, 82, 83, 108, 109]
    parse_sam(sam_filepath, remove_duplicates=True, add_aligned_sequence=True,
              extract_sequence_subset=extract_sequence_subset,
              chunksize=10000, write_csv=False, write_nc=True)

    nc_filepath = sam_filepath.with_suffix('.nc')
    fastq_filepath = r'N:\tnw\BN\CMJ\Shared\Ivo\PhD_data\20211011 - Sequencer (MiSeq)\Analysis\Index1.fastq'
    add_sequence_data_to_dataset(nc_filepath, fastq_filepath, 'index1')

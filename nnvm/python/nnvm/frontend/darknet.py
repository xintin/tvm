# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""
DarkNet symbol frontend.
"""

from __future__ import absolute_import as _abs
import numpy as np
import tvm
from .. import symbol as _sym
from .common import get_nnvm_op, required_attr, parse_tshape, parse_bool_str

class LAYERTYPE(object):
    """Darknet LAYERTYPE Class constant."""
    CONVOLUTIONAL = 0
    DECONVOLUTIONAL = 1
    CONNECTED = 2
    MAXPOOL = 3
    SOFTMAX = 4
    DETECTION = 5
    DROPOUT = 6
    CROP = 7
    ROUTE = 8
    COST = 9
    NORMALIZATION = 10
    AVGPOOL = 11
    LOCAL = 12
    SHORTCUT = 13
    ACTIVE = 14
    RNN = 15
    GRU = 16
    LSTM = 17
    CRNN = 18
    BATCHNORM = 19
    NETWORK = 20
    XNOR = 21
    REGION = 22
    YOLO = 23
    REORG = 24
    UPSAMPLE = 25
    LOGXENT = 26
    L2NORM = 27
    BLANK = 28

class ACTIVATION(object):
    """Darknet ACTIVATION Class constant."""
    LOGISTIC = 0
    RELU = 1
    RELIE = 2
    LINEAR = 3
    RAMP = 4
    TANH = 5
    PLSE = 6
    LEAKY = 7
    ELU = 8
    LOGGY = 9
    STAIR = 10
    HARDTAN = 11
    LHTAN = 12

__all__ = ['from_darknet']

def _darknet_maxpooling(inputs, attrs):
    """Process the max pool 2d operation."""
    kernel = parse_tshape(required_attr(attrs, 'kernel', 'maxpool'))
    if len(kernel) != 1:
        raise tvm.error.OpAttributeUnImplemented(
            'Non-2D kernels for Max Pooling are not supported in frontend Darknet.')

    op_name, new_attrs = 'max_pool2d', {}
    strides = int(attrs.get('stride', (1, 1)))
    pads = int(attrs.get('pad', (0, 0)))
    new_attrs['pool_size'] = [kernel[0], kernel[0]]
    new_attrs['strides'] = str((strides, strides))
    new_attrs['padding'] = str((pads, pads))
    extra_pad_size = attrs.get('extra_pad_size', 0)
    if extra_pad_size:
        pad_width = ((0, 0), (0, 0), (0, extra_pad_size), (0, extra_pad_size))
        inputs = _sym.pad(*inputs, pad_width=pad_width, pad_value=np.finfo(np.float32).min)
    return get_nnvm_op(op_name)(*inputs, **new_attrs), None

def _darknet_avgpooling(inputs, attrs):
    """Process the average pool 2d operation."""
    kernel = parse_tshape(required_attr(attrs, 'kernel', 'avgpool'))
    if len(kernel) != 1:
        raise tvm.error.OpAttributeUnimplemented(
            'Non-2D kernels for Average Pooling are not supported in frontend Darknet.')

    op_name, new_attrs = 'avg_pool2d', {}
    strides = int(attrs.get('stride', (1, 1)))
    pads = int(attrs.get('pad', (0, 0)))
    new_attrs['pool_size'] = [kernel[0], kernel[0]]
    new_attrs['strides'] = str((strides, strides))
    new_attrs['padding'] = str((pads, pads))

    return get_nnvm_op(op_name)(*inputs, **new_attrs), None

def _darknet_batch_norm(inputs, attrs):
    """Process the batchnormalization operation."""
    op_name, new_attrs = 'darknet_batch_norm', {}
    new_attrs['axis'] = attrs.get('axis', 1)
    new_attrs['epsilon'] = attrs.get('eps', 0.000001)
    new_attrs['center'] = True
    new_attrs['scale'] = True
    return get_nnvm_op(op_name)(*inputs, **new_attrs), None

def _darknet_conv2d(inputs, attrs):
    """Process the convolution 2d operation."""
    kernel = parse_tshape(required_attr(attrs, 'kernel', 'conv2d'))
    if len(kernel) != 1:
        raise tvm.error.OpAttributeUnimplemented('Non-2D kernels for Conv2D are unsupported '
                                                 'in frontend Darknet.')
    layout = attrs.get('layout', 'NCHW')
    if layout not in ['NCHW', 'NHWC']:
        raise tvm.error.OpAttributeInvalid(
            'Value {} in attribute "layout" of operator Conv2D is not valid.'.format(layout))
    strides = int(attrs.get('stride', (1, 1)))
    pads = int(attrs.get('pad', (0, 0)))

    op_name, new_attrs = 'conv2d', {}
    new_attrs['channels'] = required_attr(attrs, 'num_filter', 'conv2d')
    new_attrs['kernel_size'] = [kernel[0], kernel[0]]
    new_attrs['strides'] = (strides, strides)
    new_attrs['padding'] = (pads, pads)
    new_attrs['dilation'] = attrs.get('dilate', (1, 1))
    new_attrs['groups'] = attrs.get('num_group', 1)
    new_attrs['layout'] = layout
    if attrs.get('use_batchNorm', False) is True:
        new_attrs['use_bias'] = False
    else:
        new_attrs['use_bias'] = True
    out_name = {}
    sym = get_nnvm_op(op_name)(*inputs, **new_attrs)
    out_name[0] = sym.list_output_names()[0].replace('_output', '')

    if attrs.get('use_batchNorm', False) is True:
        op_name, new_attrs = 'batch_norm', {}
        new_attrs['epsilon'] = 0.000001
        sym = get_nnvm_op(op_name)(*sym, **new_attrs)
        out_name[1] = sym.list_output_names()[0].replace('_output', '')
    if 'activation' in attrs:
        new_attrs = {}
        new_attrs['activation'] = attrs['activation']
        new_attrs['slope'] = 0.1
        sym, _ = _darknet_activations(sym, new_attrs)
    return sym, out_name


def _darknet_conv2d_transpose(inputs, attrs):
    """Process the convolution 2d transpose operation."""
    if 'target_shape' in attrs:
        raise tvm.error.OpAttributeUnimplemented(
            'Attribute "target_shape" is not supported in operator Conv2D-transpose.')
    kernel = parse_tshape(required_attr(attrs, 'kernel', 'conv2d_transpose'))
    if len(kernel) != 2:
        raise tvm.error.OpAttributeUnimplemented(
            'Non-2D kernels are not supported in operator Conv2D-transpose.')
    layout = attrs.get('layout', 'NCHW')
    if layout not in ['NCHW', 'NHWC']:
        msg = 'Value {} in attribute "layout" of operator Conv2D-transpose is not valid.'
        raise tvm.error.OpAttributeInvalid(msg.format(layout))
    op_name, new_attrs = 'conv2d_transpose', {}
    new_attrs['channels'] = required_attr(attrs, 'num_filter', 'conv2d_transpose')
    new_attrs['kernel_size'] = kernel
    new_attrs['strides'] = attrs.get('stride', (1, 1))
    new_attrs['output_padding'] = attrs.get('adj', (0, 0))
    new_attrs['padding'] = attrs.get('pad', (0, 0))
    new_attrs['dilation'] = attrs.get('dilate', (1, 1))
    new_attrs['groups'] = attrs.get('num_group', 1)
    new_attrs['layout'] = layout
    new_attrs['use_bias'] = not parse_bool_str(attrs, 'no_bias')
    return get_nnvm_op(op_name)(*inputs, **new_attrs), None

def _darknet_shortcut(inputs, attrs):
    """Process the shortcut operation."""
    op_name, new_attrs = 'elemwise_add', {}
    input_0 = inputs[0]
    input_1 = inputs[1]
    input_0_channel = int(attrs['out_channel'])
    input_1_channel = int(attrs['add_out_channel'])
    input_0_size = int(attrs['out_size'])
    input_1_size = int(attrs['add_out_size'])

    if input_0_size > input_1_size:
        scale = int(input_0_size/input_1_size)
        input_1 = _sym.upsampling(input_1, scale=scale, name="_upsampling")
    elif input_0_size < input_1_size:
        stride = int(input_1_size/input_0_size)
        input_1 = _sym.avg_pool2d(input_1, pool_size=(1, 1),
                                  strides=(stride, stride), padding=(0, 0), name="_downsampling")

    if input_0_channel != input_1_channel:
        pad_channel = input_0_channel - input_1_channel
        input_1 = _sym.pad(input_1, pad_width=((0, 0), (0, pad_channel), (0, 0), (0, 0)),
                           pad_value=0.)

    new_inputs = _as_list([input_0, input_1])
    sym = get_nnvm_op(op_name)(*new_inputs, **new_attrs)
    out_name = sym.list_output_names()[0].replace('_output', '')
    if 'activation' in attrs:
        new_attrs['activation'] = attrs['activation']
        sym, _ = _darknet_activations(sym, new_attrs)
    return sym, out_name

def _darknet_dense(inputs, attrs):
    """Process the dense operation."""
    op_name, new_attrs = 'dense', {}
    new_attrs['units'] = required_attr(attrs, 'num_hidden', 'dense')
    out_name = {}
    new_attrs['use_bias'] = attrs.get('use_bias', False)
    if attrs.get('use_flatten', False) is True:
        inputs[0] = _sym.flatten(inputs[0])
    sym = get_nnvm_op(op_name)(*inputs, **new_attrs)
    out_name[0] = sym.list_output_names()[0].replace('_output', '')
    if 'use_batchNorm' in attrs:
        op_name, new_attrs = 'batch_norm', {}
        new_attrs['epsilon'] = 0.000001
        sym = get_nnvm_op(op_name)(*sym, **new_attrs)
        out_name[1] = sym.list_output_names()[0].replace('_output', '')
    if 'activation' in attrs:
        new_attrs = {}
        new_attrs['activation'] = attrs['activation']
        sym, _ = _darknet_activations(sym, new_attrs)
    return sym, out_name

def _darknet_dropout(inputs, attrs):
    """Process the dropout operation, its a blank operation."""
    op_name, new_attrs = 'dropout', {}
    new_attrs['rate'] = attrs.get('p', 0.5)
    return get_nnvm_op(op_name)(*inputs, **new_attrs), None

def _darknet_reshape(inputs, attrs):
    """Process the reshape operation."""
    if parse_bool_str(attrs, 'reverse'):
        raise tvm.error.OpAttributeUnimplemented(
            'Attribute "reverse" is not supported in operator Reshape.')
    op_name, new_attrs = 'reshape', {}
    new_attrs['shape'] = required_attr(attrs, 'shape', 'reshape')
    return get_nnvm_op(op_name)(*inputs, **new_attrs), None

def _darknet_upsampling(inputs, attrs):
    """Process the upsampling operation."""
    op_name, new_attrs = 'upsampling', {}
    new_attrs['scale'] = attrs.get('scale', 1)
    return get_nnvm_op(op_name)(*inputs, **new_attrs), None

def _darknet_l2normalize(inputs, attrs):
    """Process the l2 normalization operation."""
    op_name, new_attrs = 'l2_normalize', {}
    new_attrs['eps'] = attrs.get('eps', 0)
    new_attrs['axis'] = attrs.get('axis', 1)
    return get_nnvm_op(op_name)(*inputs, **new_attrs), None

def _darknet_softmax_output(inputs, attrs):
    """Process the softmax operation."""
    temperature = attrs.get('temperature', 1)
    if temperature != 1:
        inputs[0] = inputs[0] / float(temperature)
    op_name, new_attrs = 'softmax', {}
    if parse_bool_str(attrs, 'multi_output'):
        new_attrs['axis'] = 1

    if attrs.get('use_flatten', False) is True:
        inputs[0] = _sym.flatten(inputs[0])
    return get_nnvm_op(op_name)(*inputs, **new_attrs), None

def _darknet_route(inputs, attrs):
    """Process the route operation, which is equivalent to concat."""
    op_name = 'concatenate'
    new_attrs = {'axis': attrs.get('dim', 1)}
    return get_nnvm_op(op_name)(*inputs, **new_attrs), None

def _darknet_reorg(inputs, attrs):
    """Process the reorg operation."""
    op_name, new_attrs = 'yolo_reorg', {}
    if 'stride' in attrs:
        new_attrs = {'stride': attrs.get('stride', 1)}
    return get_nnvm_op(op_name)(*inputs, **new_attrs), None

def _darknet_region(inputs, attrs):
    """Process the region operation."""
    num = attrs.get('n', 1)
    classes = attrs.get('classes', 1)
    coords = attrs.get('coords', 0)
    background = attrs.get('background', 0)
    softmax = attrs.get('softmax', True)
    input_shape = attrs.get('shape')

    split_size = classes + coords + 1
    intermediate_shape = (input_shape[0], num, split_size, input_shape[2], input_shape[3])
    data_block = _sym.reshape(inputs[0], shape=intermediate_shape)
    split_indices = (2, 4, 5)
    split_res = _sym.split(data_block, indices_or_sections=split_indices, axis=2)
    split_res0 = _sym.sigmoid(split_res[0])
    if not background:
        split_res2 = _sym.sigmoid(split_res[2])
    else:
        split_res2 = split_res[2]
    if softmax:
        split_res3 = _sym.softmax(split_res[3], axis=2)
    concat_list = [split_res0, split_res[1], split_res2, split_res3]
    out = _sym.concatenate(*concat_list, axis=2)
    return _sym.reshape(out, shape=input_shape), None


def _darknet_yolo(inputs, attrs):
    """Process the yolo operation."""
    num = attrs.get('n', 1)
    classes = attrs.get('classes', 1)
    input_shape = attrs.get('shape')
    split_size = classes + 5
    intermediate_shape = (input_shape[0], num, split_size, input_shape[2], input_shape[3])
    data_block = _sym.reshape(inputs[0], shape=intermediate_shape)
    split_indices = (2, 4)
    split_res = _sym.split(data_block, indices_or_sections=split_indices, axis=2)
    split_res0 = _sym.sigmoid(split_res[0])
    split_res2 = _sym.sigmoid(split_res[2])
    concat_list = [split_res0, split_res[1], split_res2]
    out = _sym.concatenate(*concat_list, axis=2)
    return _sym.reshape(out, shape=input_shape), None

def _darknet_activations(inputs, attrs):
    """Process the activation function."""
    act = required_attr(attrs, 'activation', 'activations')
    if ACTIVATION.LOGISTIC == act:
        act_type = 'sigmoid'
    elif ACTIVATION.RELU == act:
        act_type = 'relu'
    elif ACTIVATION.TANH == act:
        act_type = 'tanh'
    elif ACTIVATION.LINEAR == act:
        return inputs, None
    elif ACTIVATION.LEAKY == act:
        act_type = 'leaky_relu'
    elif ACTIVATION.ELU == act:
        act_type = 'elu'
    else:
        raise tvm.error.OpNotImplemented(
            'Operator act: {} is not supported in framework Darknet.'.format(act))

    if act_type in ['relu', 'tanh']:
        op_name, new_attrs = act_type, {}
        sym = get_nnvm_op(op_name)(*inputs, **new_attrs)
    elif act_type in ['leaky_relu']:
        op_name, new_attrs = act_type, {}
        new_attrs['alpha'] = attrs.get('slope', 0.1)
        sym = get_nnvm_op(op_name)(*inputs, **new_attrs)
    elif act_type in ['elu']:
        sym = -1 * _sym.relu(1 - _sym.exp(*inputs)) + _sym.relu(*inputs)
    elif act_type in ['sigmoid']:
        op_name, new_attrs = act_type, {}
        sym = get_nnvm_op(op_name)(*inputs, **new_attrs)
    else:
        raise tvm.error.OpNotImplemented(
            'Operator act: {} is not supported in framework Darknet.'.format(act))
    return sym, None

def _darknet_op_not_support(inputs, attrs):
    """Raise exception if the operation is not supported."""
    err = "{} is not supported in {}.".format(attrs, inputs)
    raise NotImplementedError(err)

_DARKNET_CONVERT_MAP = {
    LAYERTYPE.CONVOLUTIONAL   : _darknet_conv2d,
    LAYERTYPE.DECONVOLUTIONAL : _darknet_conv2d_transpose,
    LAYERTYPE.CONNECTED       : _darknet_dense,
    LAYERTYPE.MAXPOOL         : _darknet_maxpooling,
    LAYERTYPE.SOFTMAX         : _darknet_softmax_output,
    LAYERTYPE.DROPOUT         : _darknet_dropout,
    LAYERTYPE.AVGPOOL         : _darknet_avgpooling,
    LAYERTYPE.BATCHNORM       : _darknet_batch_norm,
    LAYERTYPE.ROUTE           : _darknet_route,
    LAYERTYPE.REORG           : _darknet_reorg,
    LAYERTYPE.REGION          : _darknet_region,
    LAYERTYPE.SHORTCUT        : _darknet_shortcut,
    LAYERTYPE.UPSAMPLE        : _darknet_upsampling,
    LAYERTYPE.L2NORM          : _darknet_l2normalize,
    LAYERTYPE.YOLO            : _darknet_yolo,
    LAYERTYPE.DETECTION       : _darknet_op_not_support,
    LAYERTYPE.CROP            : _darknet_op_not_support,
    LAYERTYPE.COST            : _darknet_op_not_support,
    LAYERTYPE.NORMALIZATION   : _darknet_op_not_support,
    LAYERTYPE.LOCAL           : _darknet_op_not_support,
    LAYERTYPE.ACTIVE          : _darknet_op_not_support,
    LAYERTYPE.RNN             : _darknet_op_not_support,
    LAYERTYPE.GRU             : _darknet_op_not_support,
    LAYERTYPE.LSTM            : _darknet_op_not_support,
    LAYERTYPE.CRNN            : _darknet_op_not_support,
    LAYERTYPE.NETWORK         : _darknet_op_not_support,
    LAYERTYPE.XNOR            : _darknet_op_not_support,
    LAYERTYPE.BLANK           : _darknet_op_not_support,
}

def _darknet_convert_symbol(op_name, inputs, attrs):
    """Convert from darknet op to nnvm op.
    The converter must specify some conversions explicitly to
    support gluon format ops such as conv2d...

    Parameters
    ----------
    op_name : str
        Operator name, such as Convolution, Connected, etc
    inputs : list of nnvm.Symbol
        List of input symbols.
    attrs : dict
        Dict of operator attributes

    Returns
    -------
    out_name : converted out name of operation
    sym : nnvm.Symbol
        Converted nnvm Symbol
    """

    if op_name in _DARKNET_CONVERT_MAP:
        sym, out_name = _DARKNET_CONVERT_MAP[op_name](inputs, attrs)
    else:
        raise tvm.error.OpNotImplemented(
            'Operator {} is not supported in frontend Darknet.'.format(op_name))
    if out_name is  None:
        out_name = sym.list_output_names()[0].replace('_output', '')
    return out_name, sym


def _as_list(arr):
    """Force being a list, ignore if already is."""
    if isinstance(arr, list):
        return arr
    return [arr]


class GraphProto(object):
    """A helper class for handling nnvm graph copying from darknet model.
    """

    def __init__(self, net, dtype='float32'):
        self.net = net
        self.dtype = dtype
        self._sym_array = {}
        self._tvmparams = {}
        self._outs = []
        self._state_ctr = {}
        self._state_ctr['rnn'] = 0
        self._state_ctr['crnn'] = 0
        self._state_ctr['lstm'] = 0
        self._state_ctr['cell_state'] = 0
        self._state_ctr['gru'] = 0

    def _read_memory_buffer(self, shape, data, dtype=None):
        if dtype is None:
            dtype = self.dtype
        length = 1
        for x in shape:
            length *= x
        data_np = np.zeros(length, dtype=dtype)
        for i in range(length):
            data_np[i] = data[i]
        return data_np.reshape(shape)

    def _get_convolution_weights(self, layer, opname):
        """Get the convolution layer weights and biases."""
        if layer.nweights == 0:
            return

        if layer.n * layer.c * layer.size * layer.size != layer.nweights:
            msg = 'nweights ({}) != n * c * h * w ({}) in operator {}'
            msg = msg.format(layer.nweights, layer.n * layer.c * layer.size ** 2, opname)
            raise tvm.error.OpAttributeInvalid(msg)

        shape = (layer.n, layer.c, layer.size, layer.size)
        weights = self._read_memory_buffer(shape, layer.weights)

        biases = self._read_memory_buffer((layer.n, ), layer.biases)

        k = self._get_tvm_params_name(opname[0], 'weight')
        self._tvmparams[k] = tvm.nd.array(weights)

        if layer.batch_normalize == 1 and layer.dontloadscales != 1:
            self._get_batchnorm_weights(layer, opname[1], layer.n)
            k = self._get_tvm_params_name(opname[1], 'beta')
            self._tvmparams[k] = tvm.nd.array(biases)
        else:
            k = self._get_tvm_params_name(opname[0], 'bias')
            self._tvmparams[k] = tvm.nd.array(biases)

    def _get_connected_weights(self, layer, opname):
        """Parse the weights and biases for fully connected or dense layer."""
        size = layer.outputs * layer.inputs
        if size == 0:
            return

        weights = self._read_memory_buffer((layer.outputs, layer.inputs), layer.weights)
        biases = self._read_memory_buffer((layer.outputs, ), layer.biases)

        k = self._get_tvm_params_name(opname[0], 'weight')
        self._tvmparams[k] = tvm.nd.array(weights)

        if layer.batch_normalize == 1 and layer.dontloadscales != 1:
            self._get_batchnorm_weights(layer, opname[1], layer.outputs)
            k = self._get_tvm_params_name(opname[1], 'beta')
            self._tvmparams[k] = tvm.nd.array(biases)
        else:
            k = self._get_tvm_params_name(opname[0], 'bias')
            self._tvmparams[k] = tvm.nd.array(biases)

    def _get_region_weights(self, layer, opname):
        """Parse the biases for region layer."""
        biases = self._read_memory_buffer((layer.n*2, ), layer.biases)
        attributes = np.array([layer.n, layer.out_c, layer.out_h, layer.out_w,
                               layer.classes, layer.coords, layer.background],
                              dtype=np.int32)
        k = self._get_tvm_params_name(opname, 'bias')
        self._tvmparams[k] = tvm.nd.array(biases)
        k = self._get_tvm_params_name(opname, 'attr')
        self._tvmparams[k] = tvm.nd.array(attributes)

    def _get_yolo_weights(self, layer, opname):
        """Parse the biases and mask for yolo layer."""
        biases = self._read_memory_buffer((layer.total*2, ), layer.biases)
        mask = self._read_memory_buffer((layer.n, ), layer.mask, dtype='int32')
        attributes = np.array([layer.n, layer.out_c, layer.out_h, layer.out_w,
                               layer.classes, layer.total],
                              dtype=np.int32)
        k = self._get_tvm_params_name(opname, 'bias')
        self._tvmparams[k] = tvm.nd.array(biases)
        k = self._get_tvm_params_name(opname, 'mask')
        self._tvmparams[k] = tvm.nd.array(mask)
        k = self._get_tvm_params_name(opname, 'attr')
        self._tvmparams[k] = tvm.nd.array(attributes)

    def _get_batchnorm_weights(self, layer, opname, size):
        """Parse the weights for batchnorm, which includes, scales, moving mean
        and moving variances."""
        scales = self._read_memory_buffer((size, ), layer.scales)
        rolling_mean = self._read_memory_buffer((size, ), layer.rolling_mean)
        rolling_variance = self._read_memory_buffer((size, ), layer.rolling_variance)

        k = self._get_tvm_params_name(opname, 'moving_mean')
        self._tvmparams[k] = tvm.nd.array(rolling_mean)
        k = self._get_tvm_params_name(opname, 'moving_var')
        self._tvmparams[k] = tvm.nd.array(rolling_variance)
        k = self._get_tvm_params_name(opname, 'gamma')
        self._tvmparams[k] = tvm.nd.array(scales)

    def _get_darknet_attrs(self, layer, layer_num):
        """Parse attributes of each layer and return."""
        attr = {}
        use_flatten = True
        if LAYERTYPE.CONVOLUTIONAL == layer.type:
            attr.update({'layout' : 'NCHW'})
            attr.update({'pad' : str(layer.pad)})
            attr.update({'num_group' : str(layer.groups)})
            attr.update({'num_filter' : str(layer.n)})
            attr.update({'stride' : str(layer.stride)})
            attr.update({'kernel' : str(layer.size)})
            attr.update({'activation' : (layer.activation)})

            if layer.nbiases == 0:
                attr.update({'use_bias' : False})
            else:
                attr.update({'use_bias' : True})

            if layer.batch_normalize == 1 and layer.dontloadscales != 1:
                attr.update({'use_batchNorm' : True})
                attr.update({'use_scales' : True})

        elif LAYERTYPE.CONNECTED == layer.type:
            attr.update({'num_hidden' : str(layer.outputs)})
            attr.update({'activation' : (layer.activation)})
            if layer_num != 0:
                layer_prev = self.net.layers[layer_num - 1]
                if (layer_prev.out_h == layer.h and
                        layer_prev.out_w == layer.w and
                        layer_prev.out_c == layer.c):
                    use_flatten = False
            attr.update({'use_flatten' : use_flatten})
            attr.update({'use_bias' : True})
            if layer.batch_normalize == 1 and layer.dontloadscales != 1:
                attr.update({'use_batchNorm' : True})
                attr.update({'use_scales' : True})
                attr.update({'use_bias' : False})

        elif LAYERTYPE.MAXPOOL == layer.type:
            attr.update({'pad' : str(layer.pad)})
            attr.update({'stride' : str(layer.stride)})
            attr.update({'kernel' : str(layer.size)})
            max_output = (layer.w - layer.size + 2 * layer.pad)/float(layer.stride) + 1
            if max_output < layer.out_w:
                extra_pad = (layer.out_w - max_output)*layer.stride
                attr.update({'extra_pad_size' : int(extra_pad)})
        elif LAYERTYPE.AVGPOOL == layer.type:
            attr.update({'pad' : str(layer.pad)})
            if layer.stride == 0:
                attr.update({'stride' : str(1)})
            else:
                attr.update({'stride' : str(layer.stride)})
            if layer.size == 0 and layer.h == layer.w:
                attr.update({'kernel' : str(layer.h)})
            else:
                attr.update({'kernel' : str(layer.size)})

        elif LAYERTYPE.DROPOUT == layer.type:
            attr.update({'p' : str(layer.probability)})

        elif LAYERTYPE.SOFTMAX == layer.type:
            attr.update({'axis' : 1})
            attr.update({'use_flatten' : True})
            if layer.temperature:
                attr.update({'temperature' : str(layer.temperature)})

        elif LAYERTYPE.SHORTCUT == layer.type:
            add_layer = self.net.layers[layer.index]
            attr.update({'activation' : (layer.activation)})
            attr.update({'out_channel' : (layer.out_c)})
            attr.update({'out_size' : (layer.out_h)})
            attr.update({'add_out_channel' : (add_layer.out_c)})
            attr.update({'add_out_size' : (add_layer.out_h)})

        elif LAYERTYPE.ROUTE == layer.type:
            pass

        elif LAYERTYPE.COST == layer.type:
            pass

        elif LAYERTYPE.REORG == layer.type:
            attr.update({'stride' : layer.stride})

        elif LAYERTYPE.REGION == layer.type:
            attr.update({'n' : layer.n})
            attr.update({'classes' : layer.classes})
            attr.update({'coords' : layer.coords})
            attr.update({'background' : layer.background})
            attr.update({'softmax' : layer.softmax})
            attr.update({'shape' : (1, layer.c, layer.h, layer.w)})

        elif LAYERTYPE.YOLO == layer.type:
            attr.update({'n' : layer.n})
            attr.update({'classes' : layer.classes})
            attr.update({'shape' : (1, layer.c, layer.h, layer.w)})

        elif LAYERTYPE.UPSAMPLE == layer.type:
            attr.update({'scale' : layer.stride})

        elif LAYERTYPE.L2NORM == layer.type:
            pass

        else:
            raise tvm.error.OpNotImplemented(
                'Operator {} is not supported in frontend Darknet.'.format(layer.type))

        return attr

    def _get_tvm_params_name(self, opname, arg_name):
        """Makes the params name for the k,v pair."""
        return opname + '_'+ arg_name

    def _get_darknet_params(self, layer, opname):
        """To parse and get the darknet params."""
        if LAYERTYPE.CONVOLUTIONAL == layer.type:
            self._get_convolution_weights(layer, opname)

        elif LAYERTYPE.CONNECTED == layer.type:
            self._get_connected_weights(layer, opname)

        elif LAYERTYPE.REGION == layer.type:
            self._get_region_weights(layer, opname)

        elif LAYERTYPE.YOLO == layer.type:
            self._get_yolo_weights(layer, opname)
    def _preproc_layer(self, layer, layer_num):
        """To preprocess each darknet layer, some layer doesnt need processing."""
        if layer_num == 0:
            name = 'data'
            attribute = {}
            sym = [_sym.Variable(name, **attribute)]
        else:
            sym = self._sym_array[layer_num - 1]
        skip_layer = False

        if LAYERTYPE.ROUTE == layer.type:
            sym = []
            for j in range(layer.n):
                sym.append(self._sym_array[layer.input_layers[j]])
            if layer.n == 1:
                skip_layer = True

        elif LAYERTYPE.COST == layer.type:
            skip_layer = True

        elif LAYERTYPE.SHORTCUT == layer.type:
            sym = [sym, self._sym_array[layer.index]]

        elif LAYERTYPE.BLANK == layer.type:
            skip_layer = True

        if skip_layer is True:
            self._sym_array[layer_num] = sym

        return skip_layer, sym

    def _get_opname(self, layer):
        """Returs the layer name."""
        return layer.type

    def _new_rnn_state_sym(self, state=None, name='rnn'):
        """Returs a symbol for state"""
        sym_name = name + "%d_state" % self._state_ctr[name]
        self._state_ctr[name] += 1
        return _sym.Variable(name=sym_name, init=state)

    def _get_rnn_state_buffer(self, layer, name):
        """Get the state buffer for rnn."""
        buffer = np.zeros((1, layer.outputs), self.dtype)
        return self._new_rnn_state_sym(buffer, name)

    def _get_darknet_rnn_attrs(self, layer, sym):
        """Get the rnn converted symbol from attributes."""
        attr = self._get_darknet_attrs(layer, 0)
        op_name = self._get_opname(layer)
        layer_name, sym = _darknet_convert_symbol(op_name, _as_list(sym), attr)
        self._get_darknet_params(layer, layer_name)
        return sym

    def _handle_darknet_rnn_layers(self, layer_num, sym):
        """Parse attributes and handle the rnn layers."""
        attr = {}
        layer = self.net.layers[layer_num]
        processed = False

        if LAYERTYPE.RNN == layer.type:
            attr.update({'n' : layer.n})
            attr.update({'batch' : layer.batch})
            attr.update({'num_hidden' : str(layer.outputs)})

            state = self._get_rnn_state_buffer(layer, 'rnn')

            for _ in range(layer.steps):
                input_layer = layer.input_layer
                sym = self._get_darknet_rnn_attrs(input_layer, sym)

                self_layer = layer.self_layer
                state = self._get_darknet_rnn_attrs(self_layer, state)

                op_name, new_attrs = 'elemwise_add', {}
                new_inputs = _as_list([sym, state])
                state = get_nnvm_op(op_name)(*new_inputs, **new_attrs)
                self._outs.append(state)

                output_layer = layer.output_layer
                sym = self._get_darknet_rnn_attrs(output_layer, state)

            self._sym_array[layer_num] = sym
            processed = True

        elif LAYERTYPE.CRNN == layer.type:
            attr.update({'n' : layer.n})
            attr.update({'batch' : layer.batch})
            attr.update({'num_hidden' : str(layer.outputs)})

            state = self._get_rnn_state_buffer(layer, 'crnn')

            for _ in range(layer.steps):
                input_layer = layer.input_layer
                sym = self._get_darknet_rnn_attrs(input_layer, sym)

                self_layer = layer.self_layer
                state = self._get_darknet_rnn_attrs(self_layer, state)

                op_name, new_attrs = 'elemwise_add', {}
                new_inputs = _as_list([sym, state])
                state = get_nnvm_op(op_name)(*new_inputs, **new_attrs)
                self._outs.append(state)

                output_layer = layer.output_layer
                sym = self._get_darknet_rnn_attrs(output_layer, state)

            self._sym_array[layer_num] = sym
            processed = True

        elif LAYERTYPE.LSTM == layer.type:
            if layer.steps > 1:
                raise tvm.error.OpAttributeInvalid(
                    'Number of steps {} of RNN is not valid.'.format(layer.steps))

            op_name_add = 'elemwise_add'
            op_name_mul = 'elemwise_mul'
            attrs = {}
            act_attr = {}

            h_state = self._get_rnn_state_buffer(layer, 'lstm')
            c_state = self._get_rnn_state_buffer(layer, 'cell_state')
            for _ in range(layer.steps):
                sym_wf = self._get_darknet_rnn_attrs(layer.wf, h_state)
                sym_wi = self._get_darknet_rnn_attrs(layer.wi, h_state)
                sym_wg = self._get_darknet_rnn_attrs(layer.wg, h_state)
                sym_wo = self._get_darknet_rnn_attrs(layer.wo, h_state)

                input_sym = sym
                sym_uf = self._get_darknet_rnn_attrs(layer.uf, input_sym)
                sym_ui = self._get_darknet_rnn_attrs(layer.ui, input_sym)
                sym_ug = self._get_darknet_rnn_attrs(layer.ug, input_sym)
                sym_uo = self._get_darknet_rnn_attrs(layer.uo, input_sym)

                new_inputs = _as_list([sym_wf, sym_uf])
                add_f = get_nnvm_op(op_name_add)(*new_inputs, **attrs)

                new_inputs = _as_list([sym_wi, sym_ui])
                add_i = get_nnvm_op(op_name_add)(*new_inputs, **attrs)

                new_inputs = _as_list([sym_wg, sym_ug])
                add_g = get_nnvm_op(op_name_add)(*new_inputs, **attrs)

                new_inputs = _as_list([sym_wo, sym_uo])
                add_o = get_nnvm_op(op_name_add)(*new_inputs, **attrs)

                act_attr['activation'] = ACTIVATION.LOGISTIC
                act_f, _ = _darknet_activations(_as_list(add_f), act_attr)

                act_attr['activation'] = ACTIVATION.LOGISTIC
                act_i, _ = _darknet_activations(_as_list(add_i), act_attr)

                act_attr['activation'] = ACTIVATION.TANH
                act_g, _ = _darknet_activations(_as_list(add_g), act_attr)

                act_attr['activation'] = ACTIVATION.LOGISTIC
                act_o, _ = _darknet_activations(_as_list(add_o), act_attr)

                new_inputs = _as_list([act_i, act_g])
                mul_t = get_nnvm_op(op_name_mul)(*new_inputs, **attrs)

                new_inputs = _as_list([act_f, c_state])
                c_state = get_nnvm_op(op_name_mul)(*new_inputs, **attrs)

                new_inputs = _as_list([mul_t, c_state])
                c_state = get_nnvm_op(op_name_add)(*new_inputs, **attrs)

                act_attr['activation'] = ACTIVATION.TANH
                h_state, _ = _darknet_activations(_as_list(c_state), act_attr)

                new_inputs = _as_list([act_o, h_state])
                h_state = get_nnvm_op(op_name_mul)(*new_inputs, **attrs)
                self._outs = self._outs + [c_state, h_state]
                sym = h_state
            self._sym_array[layer_num] = sym
            processed = True

        elif LAYERTYPE.GRU == layer.type:
            if layer.steps > 1:
                raise tvm.error.OpAttributeInvalid(
                    'Number of steps {} is not valid in RNN.'.format(layer.steps))

            op_name_add = 'elemwise_add'
            op_name_mul = 'elemwise_mul'
            attrs = {}
            act_attr = {}

            state = self._get_rnn_state_buffer(layer, "gru")
            for _ in range(layer.steps):
                sym_wz = self._get_darknet_rnn_attrs(layer.wz, state)
                sym_wr = self._get_darknet_rnn_attrs(layer.wr, state)

                input_sym = sym
                sym_uz = self._get_darknet_rnn_attrs(layer.uz, input_sym)
                sym_ur = self._get_darknet_rnn_attrs(layer.ur, input_sym)
                sym_uh = self._get_darknet_rnn_attrs(layer.uh, input_sym)

                new_inputs = _as_list([sym_uz, sym_wz])
                add_z = get_nnvm_op(op_name_add)(*new_inputs, **attrs)

                new_inputs = _as_list([sym_ur, sym_wr])
                add_r = get_nnvm_op(op_name_add)(*new_inputs, **attrs)

                act_attr['activation'] = ACTIVATION.LOGISTIC
                act_z, _ = _darknet_activations(_as_list(add_z), act_attr)

                act_attr['activation'] = ACTIVATION.LOGISTIC
                act_r, _ = _darknet_activations(_as_list(add_r), act_attr)

                new_inputs = _as_list([act_r, state])
                forgot = get_nnvm_op(op_name_mul)(*new_inputs, **attrs)

                sym_wh = self._get_darknet_rnn_attrs(layer.wh, forgot)

                new_inputs = _as_list([sym_uh, sym_wh])
                h_state = get_nnvm_op(op_name_add)(*new_inputs, **attrs)

                if layer.tanh == 1:
                    act_attr['activation'] = ACTIVATION.TANH
                else:
                    act_attr['activation'] = ACTIVATION.LOGISTIC
                h_state, _ = _darknet_activations(_as_list(h_state), act_attr)

                sym = act_z * state + (1 - act_z) * h_state

                self._outs = self._outs + [sym]
            self._sym_array[layer_num] = sym
            processed = True

        return processed, sym

    def _make_outlist(self, sym, op_name, layer, layer_num):
        if layer.type == LAYERTYPE.REGION:
            k = self._get_tvm_params_name(op_name, 'attr')
            self._outs.insert(0, _sym.Variable(name=k, init=self._tvmparams[k].asnumpy()))
            k = self._get_tvm_params_name(op_name, 'bias')
            self._outs.insert(0, _sym.Variable(name=k, init=self._tvmparams[k].asnumpy()))
            if layer_num != self.net.n-1:
                self._outs.insert(0, sym)

        elif layer.type == LAYERTYPE.YOLO:
            k = self._get_tvm_params_name(op_name, 'attr')
            self._outs.insert(0, _sym.Variable(name=k, init=self._tvmparams[k].asnumpy()))
            k = self._get_tvm_params_name(op_name, 'bias')
            self._outs.insert(0, _sym.Variable(name=k, init=self._tvmparams[k].asnumpy()))
            k = self._get_tvm_params_name(op_name, 'mask')
            self._outs.insert(0, _sym.Variable(name=k, init=self._tvmparams[k].asnumpy()))
            if layer_num != self.net.n-1:
                self._outs.insert(0, sym)

    def from_darknet(self):
        """To convert the darknet symbol to nnvm symbols."""
        for i in range(self.net.n):
            layer = self.net.layers[i]
            need_skip, sym = self._preproc_layer(layer, i)
            if need_skip is True:
                continue

            processed, sym = self._handle_darknet_rnn_layers(i, sym)
            if processed is True:
                continue

            attr = self._get_darknet_attrs(layer, i)
            op_name = self._get_opname(layer)
            layer_name, sym = _darknet_convert_symbol(op_name, _as_list(sym), attr)
            self._get_darknet_params(self.net.layers[i], layer_name)
            self._sym_array[i] = sym
            self._make_outlist(sym, layer_name, layer, i)

        self._outs = _as_list(sym) + self._outs
        if isinstance(self._outs, list):
            sym = _sym.Group(self._outs)
        return sym, self._tvmparams

def from_darknet(net, dtype='float32'):
    """Convert from darknet's model into compatible NNVM format.
    Reconstruct a nnvm symbol by traversing the darknet input.

    Parameters
    ----------
    net : ctype Pointer to network
        Darknet parsed symbols

    dtype : str
        Datatype of the input net structure, default is float32

    Returns
    -------
    sym : nnvm.Symbol
        Compatible nnvm symbol

    params : dict of str to tvm.NDArray
        The parameter dict to be used by nnvm
    """

    return GraphProto(net, dtype).from_darknet()

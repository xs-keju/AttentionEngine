import torch
from typing import Literal
import functools
from graph import *

# TODO: support online_func extern_input_tensor

class SymbolScalar:
    def __init__(self, varname:str, value:Node):
        self.varname = varname
        self.code = value
    def __add__(self, other):
        assert isinstance(other, SymbolScalar)
        # return SymbolScalar(self.varname,f'{self.varname} = ({self.varname}+{other.varname})')
        return SymbolScalar(self.varname, Add(self.code, other.code))
    def __sub__(self, other):
        assert isinstance(other, SymbolScalar)
        return SymbolScalar(self.varname, Sub(self.code, other.code))
    
    def __mul__(self, other):
        assert isinstance(other, SymbolScalar)
        return SymbolScalar(self.varname, Mul(self.code, other.code))
    def __truediv__(self, other):
        assert isinstance(other, SymbolScalar)
        return SymbolScalar(self.varname, Div(self.code, other.code))
    def abs(self):
        return SymbolScalar(self.varname, Abs(self.code))
    def exp(self):
        return SymbolScalar(self.varname, Exp(self.code)) # TODO
    def log(self):
        return SymbolScalar(self.varname, Log(self.code)) # TODO
    def max(self, other):
        assert isinstance(other, SymbolScalar)
        return SymbolScalar(self.varname, Max(self.code, other.code))


class SymbolicArray(SymbolScalar):
    """
    Array for OnlineFunc.online_fwd
    """
    def __init__(self):
        self.code = ""
    def __add__(self, other):
        return SymbolicArray()
    def __sub__(self, other):
        return SymbolicArray()
    def __mul__(self, other):
        return SymbolicArray()
    def __truediv__(self, other):
        return SymbolicArray()
    def abs(self):
        return SymbolicArray()
    def exp(self):
        return SymbolicArray()
    def log(self):
        return SymbolicArray()
    def get_reduce(self,op:Literal["sum", "max"]):
        """
        get reduce result of array
        """
        return SymbolScalar(f' ', Var(' ')) # TODO
    
class SymbolicTensor(SymbolScalar):
    """
    Tensor for CustomIO
    """
    def __init__(self, varname:str, shape:tuple):
        super().__init__(varname, Var(varname))
        self.shape = shape
    
class CustomIO:
    def __init__(self, input_tensors:dict[str, tuple]={}):
        self.input_tensors:dict[str, SymbolicTensor] = {}
        for k,v in input_tensors.items():
            self.input_tensors[k] = SymbolicTensor(k,v)

    def __call__(self, tensor_name:str, tensor_shape:tuple):
        if tensor_name in self.input_tensors:
            raise ValueError(f"Tensor {tensor_name} already exists")
        self.input_tensors[tensor_name].shape = tensor_shape
        def decorator(func):
            def wrapper(*args, **kwargs):
            # 调用原始函数并返回结果
                result = func(*args, **kwargs)
            
                return result
            return wrapper
        return decorator


    
class OnlineFunc:
    """
    __init__: define online_rowscales and final_rowscales
        online_rowscales: intermediate scale results for online algorithm
        final_rowscales: final scale results for online algorithm

    online_fwd: online algorithm for generate attention forward

    set_final_rowscales: set final rowscales at the end of attention forward, save it for backward

    forward: forward algorithm g(scores, scale) for backward recompute
    backward: backward algorithm
    """
    def __init__(self, online_rowscales:dict[str, SymbolScalar], final_rowscales:dict[str, SymbolScalar], 
                 external_fwd_tensors:CustomIO, external_bwd_tensors:CustomIO):
        # TODO: external_tensors
        """
        define&init online_rowscales and final_rowscales
        """
        self.online_rowscales = online_rowscales
        self.final_rowscales = final_rowscales
        self.vars = {
            "scores": SymbolicArray(),
            "o_scale": None,
        }
        self.external_fwd_tensors = external_fwd_tensors
        self.external_bwd_tensors = external_bwd_tensors
        
    
    @staticmethod
    def online_fwd(scores:SymbolicArray, online_rowscales, b, h, q_idx):
        """
        compute scores, online_rowscale, o_scale
        input: 
            scores: 一维向量, 仅包含getreduce()
            online_rowscales: 在线算法的上一轮中间结果
        return:
            scores: 一维向量
            online_rowscales: 保存在线算法的更新后中间结果
            o_scale:  for online rescale o

        """
        o_scale = SymbolScalar("o_scale", Var("o_scale"))
        return scores, online_rowscales, o_scale

    @staticmethod
    def online_fwd_epilogue(o, online_rowscales, b, h, q_idx):
        """
        compute o, final_rowscales at the end of online attention forward
        return:
            o: online_fwd 最后对o进行的缩放
            final_rowscales: online_fwd执行完成后保存的scale，用于backward
        """
        final_rowscales = online_rowscales
        return o, final_rowscales

    @staticmethod
    def forward(scores, final_rowscales:dict[str, SymbolScalar], b, h, q_idx, kv_idx):
        """
        compute scores : scores = g(scores, scale), 
            final_rowscales is saved during online forward
        return 
        """
        return scores
    
    @staticmethod
    def backward(dp, scores, final_rowscales:dict[str, SymbolScalar], external_bwd_tensors, b, h, q_idx, kv_idx):
        """
        compute bwd scores: dscores = g_bwd(dp, scores)
        only support elementwise
        """
        dscores = dp
        return dscores

def create_block_mask(causal_mask, B, H, QLen, KVLen, device):
    pass

class AttentionEngine:
    def __init__(self, query, key, value, custom_fwd_inputs, custom_bwd_inputs, score_mod, block_mask,
    online_func,):
        pass

    def __call__(self, *args, **kargs):
        
        o = torch.tensor(1)
        return o

    def backward(self, *args, **kargs):
        pass
        
if __name__ == "__main__":
    online = OnlineFunc({},{}, CustomIO(), CustomIO())
    scores,online_rowscales,o_scale = online.online_fwd(SymbolicArray(), online.online_rowscales, 1, 1, 1)
    o, final_scales = online.online_fwd_epilogue(SymbolScalar("o",Var("o")), online.online_rowscales, 1, 1, 1)
    scores2 = online.forward(SymbolicArray(), online.final_rowscales, 1, 1, 1, 1)
    dscores = online.backward(SymbolScalar("dp",Var("dp")), SymbolScalar("scores",Var("scores")), online.final_rowscales, online.external_bwd_tensors, 1, 1, 1, 1)

import torch
from typing import Literal, Type
import functools
from graph import *
from utils import IndentedCode
import functools

# TODO: support online_func extern_input_tensor

def plus_count(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        self.count += 1
        for arg in args:
            if isinstance(arg, SymbolScalar):
                arg.count += 1
        return func(self, *args, **kwargs)
    return wrapper

class SymbolScalar:
    def __init__(self, varname:str, value:Node, prev=[], shape_idx:list=["block_M"]):
        self.varname = varname
        self.code = value
        self.prev = prev
        self.shape_idx = shape_idx

        self.count = 0
        self.use_list = []
        # for lower
        self.lowered = False
        self.visit_count = 0

        self.grad = None # SymbolicScalar
    
    @plus_count
    def op(self, code:Type[Node], others:list=[], shape_idx:list=None, varname_suffix:str=None):
        for i, other in enumerate(others):
            # if other is python scalar
            if isinstance(other, (int, float)):
                others[i] = SymbolicConst(other)
            else:
                assert isinstance(other, SymbolScalar)
        if shape_idx is None:
            shape_idx = self.shape_idx
        output_varname = self.varname
        if varname_suffix is not None:
            output_varname = f"{output_varname}_{varname_suffix}"

        code = code(*[x.code for x in [self]+others])
        output = self.__class__(f"{output_varname}_{self.count}", code, [self]+others, shape_idx)
        self.use_list.append(output)
        for other in others:
            other.use_list.append(output)
        return output

    def backward(self, grad=None): # SymbolicScalar
        if grad:
            self.grad = grad
        self._backward(self.grad)
        for node in self.prev:
            node.backward()

    def _backward(self, grad): # symblocscalar
        if self.code.type == "Var" or self.code.type == "Const":
            return
        if self.code.type == "Add":
            grad_0 = grad
            grad_1 = grad
            if self.prev[0].grad:
                grad_0 = grad_0 + self.prev[0].grad
            if self.prev[1].grad:
                grad_1 = grad_1 + self.prev[1].grad
            self.prev[0].grad = grad_0
            self.prev[1].grad = grad_1
        elif self.code.type == "Mul":
            grad0 = grad * self.prev[1]
            grad1 = grad * self.prev[0]
            if self.prev[0].grad:
                grad0 = grad0 + self.prev[0].grad
            if self.prev[1].grad:
                grad1 = grad1 + self.prev[1].grad
            self.prev[0].grad = grad0
            self.prev[1].grad = grad1
        elif self.code.type == "Div":
            grad0 = grad / self.prev[1]
            grad1 = - grad0 * self.prev[0] / self.prev[1]
            if self.prev[0].grad:
                grad0 = grad0 + self.prev[0].grad
            if self.prev[1].grad:
                grad1 = grad1 + self.prev[1].grad
            self.prev[0].grad = grad0
            self.prev[1].grad = grad1
        else:
            raise NotImplementedError(f"backward for {self.code.type} is not implemented")

    def clear_usecount(self):
        self.count = 0
        self.use_list.clear()
    def clear_visit(self):
        self.visit_count = 0
        self.lowered = False
    def clear_codegen(self):
        self.clear_usecount()
        self.clear_visit()

    def __add__(self, other):
        return self.op(Add, [other])

    def __neg__(self):
        return self.op(Neg)

    def __sub__(self, other):
        return self.op(Sub, [other])

    def __mul__(self, other):
        return self.op(Mul, [other])

    def __truediv__(self, other):
        return self.op(Div, [other])

    def abs(self):
        return self.op(Abs)

    def exp(self):
        return self.op(Exp)

    def log(self):
        return self.op(Log)

    def max(self, other):
        return self.op(Max, [other])


class SymbolicArray(SymbolScalar):
    """
    Array for OnlineFunc.online_fwd
    """
    def __init__(self, varname:str="", code:Node=Var(" "), prev=[], shape_idx:list=["block_M", "block_N"]):
        super().__init__(varname, code, prev, shape_idx)

    def get_reduce(self,op:Literal["sum", "max"]):
        """
        get reduce result of array
        """
        if op == "sum":
            return self.op(ReduceSum, shape_idx=self.shape_idx[:-1], varname_suffix="sum")
        elif op == "max":
            return self.op(ReduceMax, shape_idx=self.shape_idx[:-1], varname_suffix="max")
        else:
            raise NotImplementedError
    
class SymbolicTensor(SymbolScalar):
    """
    Tensor for CustomIO
    """
    def __init__(self, varname:str, shape:tuple):
        # convert shape to shape_idx
        super().__init__(varname, Var(varname), shape_idx=[str(i) for i in shape])
        self.shape = shape
    
class SymbolicConst(SymbolScalar):
    """
    Const for constant value
    """
    def __init__(self, value):
        super().__init__(str(value), Const(value), prev=[], shape_idx=[])

        
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
                 external_fwd_tensors:CustomIO): # , external_bwd_tensors:CustomIO):
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
        # self.external_bwd_tensors = external_bwd_tensors
        self.doosum_rowscales = SymbolicArray("doosum", Var("doosum"), shape_idx=["block_M"])
        
    
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
    def backward(dp, scores, final_rowscales:dict[str, SymbolScalar], b, h, q_idx, kv_idx):
        """
        compute bwd scores: dscores = g_bwd(dp, scores)
        only support elementwise
        """
        dscores = dp
        return dscores

def create_block_mask(causal_mask, B, H, QLen, KVLen, device):
    pass
        
if __name__ == "__main__":
    online = OnlineFunc({},{}, CustomIO(), CustomIO())
    scores,online_rowscales,o_scale = online.online_fwd(SymbolicArray(), online.online_rowscales, 1, 1, 1)
    o, final_scales = online.online_fwd_epilogue(SymbolScalar("o",Var("o")), online.online_rowscales, 1, 1, 1)
    scores2 = online.forward(SymbolicArray(), online.final_rowscales, 1, 1, 1, 1)
    dscores = online.backward(SymbolScalar("dp",Var("dp")), SymbolScalar("scores",Var("scores")), online.final_rowscales, online.external_bwd_tensors, 1, 1, 1, 1)

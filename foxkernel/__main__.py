from ipykernel.kernelapp import IPKernelApp
from .kernel import FoxKernel

IPKernelApp.launch_instance(kernel_class=FoxKernel)

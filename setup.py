from setuptools import setup, find_packages

setup(
    name='foxkernel',
    version='0.1.0',
    description='Jupyter kernel for the COSY INFINITY FOX language',
    author='Eremey Valetov',
    packages=find_packages(),
    install_requires=['jupyter_client', 'ipykernel'],
    entry_points={
        'console_scripts': [
            'foxkernel-install = foxkernel.install:main',
        ],
        'pygments.lexers': [
            'fox = foxkernel.fox_lexer:FoxLexer',
        ],
    },
    package_data={
        'foxkernel': ['kernel.json'],
    },
    classifiers=[
        'Framework :: Jupyter',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
    ],
)

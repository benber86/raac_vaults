from moccasin.boa_tools import VyperContract

from src import Counter


def deploy() -> VyperContract:
    counter: VyperContract = Counter.deploy()
    print("Starting count: ", counter.number())
    counter.increment()
    print("Ending count: ", counter.number())
    return counter


def moccasin_main() -> VyperContract:
    return deploy()

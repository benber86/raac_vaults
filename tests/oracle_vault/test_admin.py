import boa

from src.harvesters import oracle_harvester


def test_oracle_slippage_configuration(
    test_oracle_vault,
    harvest_manager,
    strategy_manager,
):
    vault_addr, strategy_addr, harvester_addr = test_oracle_vault
    harvester_contract = oracle_harvester.at(harvester_addr)

    with boa.env.prank(harvest_manager):
        harvester_contract.set_slippage(9500)
        assert harvester_contract.allowed_slippage() == 9500

    with boa.env.prank(harvest_manager):
        with boa.reverts("Slippage too high"):
            harvester_contract.set_slippage(8999)

    with boa.env.prank(strategy_manager):
        with boa.reverts("Manager only"):
            harvester_contract.set_slippage(9700)

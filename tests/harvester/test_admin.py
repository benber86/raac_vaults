import boa
from boa.contracts.abi.abi_contract import ABIContractFactory

from src.harvesters import curve_harvester
from tests.conftest import ZERO_ADDRESS
from tests.utils.abis import ERC20_ABI
from tests.utils.constants import (
    CRV_TOKEN,
    CURVE_CVX_ETH_POOL,
    CURVE_TRICRV_POOL,
    CVX_TOKEN,
)


def test_curve_swapper_set_approvals(test_permissioned_vault):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    harvester_contract = curve_harvester.at(harvester_addr)

    cvx_token = ABIContractFactory("ERC20", ERC20_ABI).at(CVX_TOKEN)
    crv_token = ABIContractFactory("ERC20", ERC20_ABI).at(CRV_TOKEN)

    harvester_contract.set_approvals()

    final_cvx_allowance = cvx_token.allowance(
        harvester_addr, CURVE_CVX_ETH_POOL
    )
    final_crv_allowance = crv_token.allowance(
        harvester_addr, CURVE_TRICRV_POOL
    )

    assert final_cvx_allowance == 2**256 - 1
    assert final_crv_allowance == 2**256 - 1


def test_fee_collector_set_strategy_reverts_already_set(
    test_permissioned_vault, accounts
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    harvester_contract = curve_harvester.at(harvester_addr)
    assert harvester_contract.strategy() == strategy_addr
    with boa.reverts():
        harvester_contract.set_strategy(accounts[1])


def test_fee_collector_set_strategy_reverts_zero_address():
    fresh_harvester = curve_harvester.deploy(ZERO_ADDRESS)

    with boa.reverts():
        fresh_harvester.set_strategy(ZERO_ADDRESS)


def test_fee_collector_set_strategy_success():
    fresh_harvester = curve_harvester.deploy(ZERO_ADDRESS)
    strategy_addr = "0x1234567890123456789012345678901234567890"

    fresh_harvester.set_strategy(strategy_addr)
    assert fresh_harvester.strategy() == strategy_addr

    with boa.reverts():
        fresh_harvester.set_strategy(strategy_addr)


def test_harvester_harvest_reverts_non_strategy(
    test_permissioned_vault, accounts
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    harvester_contract = curve_harvester.at(harvester_addr)
    non_strategy = accounts[1]

    with boa.env.prank(non_strategy):
        with boa.reverts("Strategy only"):
            harvester_contract.harvest(accounts[2], 0, [], b"", b"", b"")


def test_swapper_set_extra_reward_hook_reverts_non_strategy(
    test_permissioned_vault, accounts, add_liquidity_hook
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    harvester_contract = curve_harvester.at(harvester_addr)
    non_strategy = accounts[1]

    with boa.env.prank(non_strategy):
        with boa.reverts("Strategy only"):
            harvester_contract.set_extra_reward_hook(
                add_liquidity_hook.address
            )


def test_swapper_set_target_hook_reverts_non_strategy(
    test_permissioned_vault, accounts, add_liquidity_hook
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    harvester_contract = curve_harvester.at(harvester_addr)
    non_strategy = accounts[1]

    with boa.env.prank(non_strategy):
        with boa.reverts("Strategy only"):
            harvester_contract.set_target_hook(add_liquidity_hook.address)


def test_swapper_transfer_to_reward_hook_reverts_non_hook(
    test_permissioned_vault, accounts, handle_extra_rewards_hook
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    harvester_contract = curve_harvester.at(harvester_addr)
    non_hook = accounts[1]

    with boa.env.prank(strategy_addr):
        harvester_contract.set_extra_reward_hook(handle_extra_rewards_hook)

    with boa.env.prank(non_hook):
        with boa.reverts("Hook only"):
            harvester_contract.transfer_to_reward_hook(ZERO_ADDRESS, 1000)


def test_swapper_transfer_to_target_hook_reverts_non_hook(
    test_permissioned_vault, accounts, add_liquidity_hook
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    harvester_contract = curve_harvester.at(harvester_addr)
    non_hook = accounts[1]

    with boa.env.prank(strategy_addr):
        harvester_contract.set_target_hook(add_liquidity_hook)

    with boa.env.prank(non_hook):
        with boa.reverts("Hook only"):
            harvester_contract.transfer_to_target_hook(ZERO_ADDRESS, 1000)


def test_swapper_transfer_to_reward_hook_reverts_no_hook_set(
    test_permissioned_vault, handle_extra_rewards_hook
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    harvester_contract = curve_harvester.at(harvester_addr)

    with boa.env.prank(strategy_addr):
        harvester_contract.set_extra_reward_hook(ZERO_ADDRESS)

    with boa.env.prank(handle_extra_rewards_hook.address):
        with boa.reverts("No hook set"):
            harvester_contract.transfer_to_reward_hook(ZERO_ADDRESS, 1000)


def test_swapper_transfer_to_target_hook_reverts_no_hook_set(
    test_permissioned_vault, add_liquidity_hook
):
    vault_addr, strategy_addr, harvester_addr = test_permissioned_vault

    harvester_contract = curve_harvester.at(harvester_addr)

    with boa.env.prank(strategy_addr):
        harvester_contract.set_target_hook(ZERO_ADDRESS)

    with boa.env.prank(add_liquidity_hook.address):
        with boa.reverts("No hook set"):
            harvester_contract.transfer_to_target_hook(ZERO_ADDRESS, 1000)

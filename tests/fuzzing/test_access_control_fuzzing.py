import boa
import pytest
from boa.contracts.abi.abi_contract import ABIContractFactory
from boa.test import strategies as boa_st
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from src import raac_vault, strategy
from src.harvesters import curve_harvester
from tests.utils.abis import ERC20_ABI
from tests.utils.constants import (
    CRV_TOKEN,
    CVX_TOKEN,
    MAX_CALLER_FEE,
    MAX_PLATFORM_FEE,
    ZERO_ADDRESS,
)


class TestAccessControlFuzzing:

    def _setup_vault_components(self, pyusd_vault):
        vault_addr, strategy_addr, harvester_addr = pyusd_vault
        vault = raac_vault.at(vault_addr)
        strategy_contract = strategy.at(strategy_addr)
        harvester_contract = curve_harvester.at(harvester_addr)
        lp_token_addr = vault.asset()
        lp_token = ABIContractFactory("ERC20", ERC20_ABI).at(lp_token_addr)
        return vault, lp_token, strategy_contract, harvester_contract

    @given(
        caller=boa_st.strategy("address"),
        platform_fee=st.integers(min_value=0, max_value=MAX_PLATFORM_FEE * 2),
    )
    @settings(max_examples=50, deadline=30000)
    def test_set_platform_fee_unauthorized(
        self, pyusd_vault, caller, platform_fee
    ):
        vault, lp_token, strategy_contract, harvester = (
            self._setup_vault_components(pyusd_vault)
        )
        assume(caller != vault.address)
        pre_fee = strategy_contract.platform_fee()
        with boa.env.prank(caller):
            with boa.reverts("Vault only"):
                strategy_contract.set_platform_fee(platform_fee)
        assert strategy_contract.platform_fee() == pre_fee

    @pytest.mark.parametrize("v", [0, MAX_PLATFORM_FEE - 1, MAX_PLATFORM_FEE])
    def test_set_platform_fee_bounds(self, pyusd_vault, v):
        vault, lp_token, strategy_contract, harvester = (
            self._setup_vault_components(pyusd_vault)
        )
        with boa.env.prank(vault.address):
            if v <= MAX_PLATFORM_FEE:
                strategy_contract.set_platform_fee(v)
                assert strategy_contract.platform_fee() == v
            else:
                with boa.reverts("Fee too high"):
                    strategy_contract.set_platform_fee(v)

    @given(
        caller=boa_st.strategy("address"),
        caller_fee=st.integers(min_value=0, max_value=MAX_CALLER_FEE * 2),
    )
    @settings(max_examples=50, deadline=30000)
    def test_set_caller_fee_unauthorized(
        self, pyusd_vault, caller, caller_fee
    ):
        vault, lp_token, strategy_contract, harvester = (
            self._setup_vault_components(pyusd_vault)
        )
        assume(caller != vault.address)
        pre_fee = strategy_contract.caller_fee()
        with boa.env.prank(caller):
            with boa.reverts("Vault only"):
                strategy_contract.set_caller_fee(caller_fee)
        assert strategy_contract.caller_fee() == pre_fee

    @pytest.mark.parametrize("v", [0, MAX_CALLER_FEE - 1, MAX_CALLER_FEE])
    def test_set_caller_fee_bounds(self, pyusd_vault, v):
        vault, lp_token, strategy_contract, harvester = (
            self._setup_vault_components(pyusd_vault)
        )
        with boa.env.prank(vault.address):
            if v <= MAX_CALLER_FEE:
                strategy_contract.set_caller_fee(v)
                assert strategy_contract.caller_fee() == v
            else:
                with boa.reverts("Fee too high"):
                    strategy_contract.set_caller_fee(v)

    @given(
        caller=boa_st.strategy("address"),
        new_harvester=boa_st.strategy("address"),
    )
    @settings(max_examples=50, deadline=30000)
    def test_update_harvester_unauthorized(
        self, pyusd_vault, caller, new_harvester
    ):
        vault, lp_token, strategy_contract, harvester = (
            self._setup_vault_components(pyusd_vault)
        )
        assume(caller != vault.address)
        pre_harvester = strategy_contract.harvester()
        with boa.env.prank(caller):
            with boa.reverts("Vault only"):
                strategy_contract.update_harvester(new_harvester)
        assert strategy_contract.harvester() == pre_harvester

    def test_update_harvester_authorized(self, pyusd_vault):
        vault, lp_token, strategy_contract, harvester = (
            self._setup_vault_components(pyusd_vault)
        )
        new_valid_harvester = boa.env.generate_address()
        with boa.env.prank(vault.address):
            strategy_contract.update_harvester(new_valid_harvester)
            assert strategy_contract.harvester() == new_valid_harvester
            with boa.reverts("Zero address"):
                strategy_contract.update_harvester(ZERO_ADDRESS)

    @given(
        caller=boa_st.strategy("address"), new_hook=boa_st.strategy("address")
    )
    @settings(max_examples=50, deadline=30000)
    def test_set_extra_reward_hook_unauthorized(
        self, pyusd_vault, caller, new_hook
    ):
        vault, lp_token, strategy_contract, harvester = (
            self._setup_vault_components(pyusd_vault)
        )
        assume(caller != vault.address)
        pre_hook = harvester.extra_reward_hook()
        with boa.env.prank(caller):
            with boa.reverts("Vault only"):
                strategy_contract.set_extra_reward_hook(new_hook)
        assert harvester.extra_reward_hook() == pre_hook

    def test_set_extra_reward_hook_authorized(self, pyusd_vault):
        vault, lp_token, strategy_contract, harvester = (
            self._setup_vault_components(pyusd_vault)
        )
        new_hook = boa.env.generate_address()
        with boa.env.prank(vault.address):
            strategy_contract.set_extra_reward_hook(new_hook)
            assert harvester.extra_reward_hook() == new_hook
            strategy_contract.set_extra_reward_hook(ZERO_ADDRESS)
            assert harvester.extra_reward_hook() == ZERO_ADDRESS

    @given(
        caller=boa_st.strategy("address"),
        target_hook=boa_st.strategy("address"),
    )
    @settings(max_examples=50, deadline=30000)
    def test_set_target_hook_unauthorized(
        self, pyusd_vault, caller, target_hook
    ):
        vault, lp_token, strategy_contract, harvester = (
            self._setup_vault_components(pyusd_vault)
        )
        assume(caller != vault.address)
        pre_hook = harvester.target_hook()
        with boa.env.prank(caller):
            with boa.reverts("Vault only"):
                strategy_contract.set_target_hook(target_hook)
        assert harvester.target_hook() == pre_hook

    def test_set_target_hook_authorized(self, pyusd_vault):
        vault, lp_token, strategy_contract, harvester = (
            self._setup_vault_components(pyusd_vault)
        )
        new_hook = boa.env.generate_address()
        with boa.env.prank(vault.address):
            strategy_contract.set_target_hook(new_hook)
            assert harvester.target_hook() == new_hook
            strategy_contract.set_target_hook(ZERO_ADDRESS)
            assert harvester.target_hook() == ZERO_ADDRESS

    @given(
        caller=boa_st.strategy("address"),
        deposit_amount=st.integers(min_value=1, max_value=10**25),
    )
    @settings(max_examples=50, deadline=30000)
    def test_strategy_deposit_unauthorized(
        self, pyusd_vault, caller, deposit_amount
    ):
        vault, lp_token, strategy_contract, harvester = (
            self._setup_vault_components(pyusd_vault)
        )
        assume(caller != vault.address)
        boa.deal(lp_token, strategy_contract.address, deposit_amount)
        pre_assets = strategy_contract.total_assets()
        with boa.env.prank(caller):
            with boa.reverts("Vault only"):
                strategy_contract.deposit(deposit_amount)
        assert strategy_contract.total_assets() == pre_assets

    def test_strategy_deposit_authorized(self, pyusd_vault):
        vault, lp_token, strategy_contract, harvester = (
            self._setup_vault_components(pyusd_vault)
        )
        deposit_amount = 10**18
        boa.deal(lp_token, strategy_contract.address, deposit_amount)
        pre_assets = strategy_contract.total_assets()
        with boa.env.prank(vault.address):
            strategy_contract.deposit(deposit_amount)
        assert strategy_contract.total_assets() >= pre_assets

    @given(
        caller=boa_st.strategy("address"),
        withdraw_amount=st.integers(min_value=1, max_value=10**25),
        receiver=boa_st.strategy("address"),
    )
    @settings(max_examples=50, deadline=30000)
    def test_strategy_withdraw_unauthorized(
        self, pyusd_vault, caller, withdraw_amount, receiver
    ):
        vault, lp_token, strategy_contract, harvester = (
            self._setup_vault_components(pyusd_vault)
        )
        assume(caller != vault.address)
        assume(receiver != ZERO_ADDRESS)
        initial_deposit = max(withdraw_amount * 2, 10**18)
        boa.deal(lp_token, strategy_contract.address, initial_deposit)
        with boa.env.prank(vault.address):
            strategy_contract.deposit(initial_deposit)
        pre_assets = strategy_contract.total_assets()
        pre_balance = lp_token.balanceOf(receiver)
        with boa.env.prank(caller):
            with boa.reverts("Vault only"):
                strategy_contract.withdraw(withdraw_amount, receiver)
        assert strategy_contract.total_assets() == pre_assets
        assert lp_token.balanceOf(receiver) == pre_balance

    def test_strategy_withdraw_authorized(self, pyusd_vault):
        vault, lp_token, strategy_contract, harvester = (
            self._setup_vault_components(pyusd_vault)
        )

        initial_deposit = 10**18
        withdraw_amount = initial_deposit // 2
        receiver = boa.env.generate_address()

        boa.deal(lp_token, strategy_contract.address, initial_deposit)
        with boa.env.prank(vault.address):
            strategy_contract.deposit(initial_deposit)

        pre_assets = strategy_contract.total_assets()
        pre_balance = lp_token.balanceOf(receiver)

        with boa.env.prank(vault.address):
            strategy_contract.withdraw(withdraw_amount, receiver)

        assert strategy_contract.total_assets() < pre_assets
        assert lp_token.balanceOf(receiver) > pre_balance

    @given(
        caller=boa_st.strategy("address"),
        harvest_caller=boa_st.strategy("address"),
        min_amount_out=st.integers(min_value=0, max_value=10**18),
        extra_rewards=st.one_of(
            st.just([]), st.lists(boa_st.strategy("address"), max_size=3)
        ),
    )
    @settings(max_examples=30, deadline=60000)
    def test_harvest_unauthorized(
        self,
        pyusd_vault,
        caller,
        harvest_caller,
        min_amount_out,
        extra_rewards,
    ):
        vault, lp_token, strategy_contract, harvester = (
            self._setup_vault_components(pyusd_vault)
        )
        assume(caller != vault.address)
        assume(harvest_caller != ZERO_ADDRESS)
        with boa.env.prank(caller):
            with boa.reverts("Vault only"):
                strategy_contract.harvest(
                    harvest_caller,
                    min_amount_out,
                    extra_rewards,
                    b"",
                    b"",
                    b"",
                )

    def test_harvest_authorized(self, pyusd_vault):
        vault, lp_token, strategy_contract, harvester = (
            self._setup_vault_components(pyusd_vault)
        )
        harvest_caller = boa.env.generate_address()
        min_amount_out = 0
        extra_rewards = []
        pre_last_harvest = vault.last_harvest()
        with boa.env.prank(vault.address):
            try:
                strategy_contract.harvest(
                    harvest_caller,
                    min_amount_out,
                    extra_rewards,
                    b"",
                    b"",
                    b"",
                )
                post_last_harvest = vault.last_harvest()
                assert post_last_harvest >= pre_last_harvest
            except Exception as e:
                assert "Vault only" not in str(e)

    @given(caller=boa_st.strategy("address"))
    @settings(max_examples=50, deadline=30000)
    def test_set_approvals_permissionless(self, pyusd_vault, caller):
        vault, lp_token, strategy_contract, harvester = (
            self._setup_vault_components(pyusd_vault)
        )
        with boa.env.prank(caller):
            strategy_contract.set_approvals()

    @given(
        caller=boa_st.strategy("address"),
        recipient=boa_st.strategy("address"),
        tokens=st.lists(boa_st.strategy("address"), min_size=1, max_size=12),
    )
    @settings(max_examples=30, deadline=30000)
    def test_forward_tokens_unauthorized(
        self, pyusd_vault, caller, recipient, tokens
    ):
        vault, lp_token, strategy_contract, harvester = (
            self._setup_vault_components(pyusd_vault)
        )
        assume(caller != vault.address)
        assume(recipient != ZERO_ADDRESS)
        with boa.env.prank(caller):
            with boa.reverts("Vault only"):
                strategy_contract.forward_tokens(tokens, recipient)

    def test_forward_tokens_authorized(self, pyusd_vault):
        vault, lp_token, strategy_contract, harvester = (
            self._setup_vault_components(pyusd_vault)
        )
        recipient = boa.env.generate_address()
        tokens = [CRV_TOKEN, CVX_TOKEN]
        with boa.env.prank(vault.address):
            strategy_contract.forward_tokens(tokens, recipient)

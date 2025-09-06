from collections import namedtuple
from fractions import Fraction

import boa
import pytest
from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    invariant,
    precondition,
    rule,
    run_state_machine_as_test,
)

VaultState = namedtuple(
    "VaultState",
    [
        "raw_total_supply",
        "raw_vault_balance",
        "unlocked_shares",
        "locked_shares",
        "ext_total_supply",
        "total_assets",
        "price_per_share",
    ],
)


class StatefulVault(RuleBasedStateMachine):
    user_id = st.integers(min_value=0, max_value=9)
    deposit_amount = st.integers(min_value=1000, max_value=100_000)
    withdraw_fraction = st.floats(
        min_value=0.1, max_value=1.0, allow_nan=False, allow_infinity=False
    )
    harvest_amount = st.integers(min_value=5000, max_value=50_000)
    time_advance = st.integers(
        min_value=3600, max_value=86400 * 7
    )  # 1 hour to 1 week
    operation_type = st.integers(min_value=0, max_value=9)
    wait_flag = st.booleans()

    def __init__(self):
        super().__init__()
        self.step_count = 0
        self.last_state = None

        for i, user in enumerate(self.accounts):
            boa.deal(self.crvusd_token, user, 100_000_000 * 10**18)
            with boa.env.prank(user):
                self.crvusd_token.approve(self.mock_vault.address, 2**256 - 1)

        print("\n")
        print("=" * 80)
        print(f"Users: {len(self.accounts)}")
        print(f"Initial vault state: {self._get_vault_state()}")

    def _get_vault_state(self):
        raw_total = self.mock_vault.raw_total_supply()
        raw_vault_bal = self.mock_vault.raw_vault_balance()
        unlocked = self.mock_vault.unlocked_shares()
        locked = self.mock_vault.locked_shares()
        ext_total = raw_total - unlocked
        total_assets = self.mock_vault.totalAssets()
        price_per_share = (
            (total_assets * 10**18 // ext_total) if ext_total > 0 else 10**18
        )

        return VaultState(
            raw_total_supply=raw_total,
            raw_vault_balance=raw_vault_bal,
            unlocked_shares=unlocked,
            locked_shares=locked,
            ext_total_supply=ext_total,
            total_assets=total_assets,
            price_per_share=price_per_share,
        )

    @rule(amount=deposit_amount, uid=user_id)
    def deposit(self, amount, uid):
        user = self.accounts[uid]
        amount_wei = amount * 10**18

        strategy_assets_before = self.mock_strategy_contract.total_assets()
        vault_state_before = self._get_vault_state()

        self.step_count += 1
        print(f"\n--- Step {self.step_count}: DEPOSIT ---")
        print(f"User {uid} depositing {amount:,.0f} crvUSD")
        print(
            f"Strategy assets before: {strategy_assets_before / 10**18:,.2f}"
        )
        print(
            f"Vault state before: totalAssets={vault_state_before.total_assets / 10**18:,.2f}, extTotal={vault_state_before.ext_total_supply / 10**18:,.2f}"
        )

        with boa.env.prank(user):
            shares_received = self.mock_vault.deposit(amount_wei, user)

            strategy_assets_after = self.mock_strategy_contract.total_assets()

            print(f"Shares received: {shares_received / 10**18:,.2f}")
            print(
                f"Strategy assets after: {strategy_assets_after / 10**18:,.2f} (change: {(strategy_assets_after - strategy_assets_before) / 10**18:,.2f})"
            )

            strategy_delta = strategy_assets_after - strategy_assets_before
            assert strategy_delta == pytest.approx(
                amount_wei, abs=1
            ), f"Strategy conservation failed: expected change={amount_wei}, actual change={strategy_delta}"

            new = self._get_vault_state()
            assert (
                new.ext_total_supply - vault_state_before.ext_total_supply
                == shares_received
            )

            roundtrip_assets = self.mock_vault.previewRedeem(shares_received)
            assert roundtrip_assets == pytest.approx(
                amount_wei, rel=1e-5
            ), f"Round-trip failed: {amount_wei} -> {shares_received} -> {roundtrip_assets}"

    @rule(frac=withdraw_fraction, uid=user_id)
    def withdraw(self, frac, uid):
        user = self.accounts[uid]
        user_shares = self.mock_vault.balanceOf(user)

        if user_shares == 0:
            return

        f = Fraction(frac).limit_denominator(10**12)
        shares_to_withdraw = user_shares * f.numerator // f.denominator
        if shares_to_withdraw == 0:
            return

        strategy_assets_before = self.mock_strategy_contract.total_assets()
        vault_state_before = self._get_vault_state()

        self.step_count += 1
        print(f"\n--- Step {self.step_count}: WITHDRAW ---")
        print(
            f"User {uid} withdrawing {frac:.1%} of shares ({shares_to_withdraw / 10**18:,.2f})"
        )
        print(
            f"Strategy assets before: {strategy_assets_before / 10**18:,.2f}"
        )
        print(
            f"Vault state before: totalAssets={vault_state_before.total_assets / 10**18:,.2f}"
        )

        with boa.env.prank(user):
            max_withdraw = self.mock_vault.maxWithdraw(user)
            assets_to_withdraw = min(
                max_withdraw, self.mock_vault.previewRedeem(shares_to_withdraw)
            )

            self.mock_vault.withdraw(assets_to_withdraw, user, user)

            strategy_assets_after = self.mock_strategy_contract.total_assets()

            print(f"Assets withdrawn: {assets_to_withdraw / 10**18:,.2f}")
            print(
                f"Strategy assets after: {strategy_assets_after / 10**18:,.2f} (change: {(strategy_assets_after - strategy_assets_before) / 10**18:,.2f})"
            )

            strategy_delta = strategy_assets_after - strategy_assets_before
            assert strategy_delta == pytest.approx(
                -assets_to_withdraw, abs=1
            ), f"Strategy conservation failed: expected change={-assets_to_withdraw}, actual change={strategy_delta}"

            new = self._get_vault_state()
            expected_shares_burned = self.mock_vault.previewWithdraw(
                assets_to_withdraw
            )
            assert (
                vault_state_before.ext_total_supply - new.ext_total_supply
                == pytest.approx(expected_shares_burned, abs=1)
            )

    @rule(shares=deposit_amount, uid=user_id)
    def mint(self, shares, uid):
        user = self.accounts[uid]
        shares_wei = shares * 10**18

        max_mint = self.mock_vault.maxMint(user)
        if shares_wei > max_mint:
            shares_wei = max_mint

        if shares_wei == 0:
            return

        assets_required_preview = self.mock_vault.previewMint(shares_wei)
        user_balance = self.crvusd_token.balanceOf(user)

        if assets_required_preview > user_balance:
            return

        strategy_before = self.mock_strategy_contract.total_assets()
        before = self._get_vault_state()

        self.step_count += 1
        print(f"\n--- Step {self.step_count}: MINT ---")
        print(f"User {uid} minting {shares_wei / 10**18:,.0f} shares")
        print(f"Strategy assets before: {strategy_before / 10**18:,.2f}")

        with boa.env.prank(user):
            assets_required = self.mock_vault.mint(shares_wei, user)

        strategy_after = self.mock_strategy_contract.total_assets()
        after = self._get_vault_state()

        print(f"Assets required: {assets_required / 10**18:,.2f}")
        print(
            f"Strategy assets after: {strategy_after / 10**18:,.2f} (change: {(strategy_after - strategy_before) / 10**18:,.2f})"
        )

        assert after.ext_total_supply - before.ext_total_supply == shares_wei
        assert strategy_after - strategy_before == pytest.approx(
            assets_required, abs=1
        )
        assert self.mock_vault.previewRedeem(shares_wei) == pytest.approx(
            assets_required, rel=1e-5
        )

    @rule(frac=withdraw_fraction, uid=user_id)
    def redeem(self, frac, uid):
        user = self.accounts[uid]
        user_shares = self.mock_vault.balanceOf(user)

        if user_shares == 0:
            return

        f = Fraction(frac).limit_denominator(10**12)
        shares_to_redeem = user_shares * f.numerator // f.denominator
        if shares_to_redeem == 0:
            return

        strategy_assets_before = self.mock_strategy_contract.total_assets()
        vault_state_before = self._get_vault_state()

        self.step_count += 1
        print(f"\n--- Step {self.step_count}: REDEEM ---")
        print(
            f"User {uid} redeeming {frac:.1%} of shares ({shares_to_redeem / 10**18:,.2f})"
        )
        print(
            f"Strategy assets before: {strategy_assets_before / 10**18:,.2f}"
        )

        with boa.env.prank(user):
            max_redeem = self.mock_vault.maxRedeem(user)
            shares_to_redeem = min(max_redeem, shares_to_redeem)

            assets_received = self.mock_vault.redeem(
                shares_to_redeem, user, user
            )

            strategy_assets_after = self.mock_strategy_contract.total_assets()

            print(f"Assets received: {assets_received / 10**18:,.2f}")
            print(
                f"Strategy assets after: {strategy_assets_after / 10**18:,.2f} (change: {(strategy_assets_after - strategy_assets_before) / 10**18:,.2f})"
            )

            strategy_delta = strategy_assets_after - strategy_assets_before
            assert strategy_delta == pytest.approx(
                -assets_received, abs=1
            ), f"Strategy conservation failed: expected change={-assets_received}, actual change={strategy_delta}"

            new = self._get_vault_state()
            assert (
                vault_state_before.ext_total_supply - new.ext_total_supply
                == shares_to_redeem
            )

    @rule(
        amount=harvest_amount,
        dt=time_advance,
        op_type=operation_type,
        wait=wait_flag,
    )
    @precondition(lambda self: self.mock_vault.totalSupply() > 0)
    # this precondition excludes donation/inflation attack scenarios for freshly deployed vaults
    # which should be mitigated with the _seed param on vault deployment via the facatory
    def harvest_or_donate(self, amount, op_type, dt, wait):
        amount_wei = amount * 10**18

        if op_type == 9:
            self._donate(amount_wei)
        else:
            self._harvest(amount_wei)
        if wait:
            boa.env.time_travel(dt)

    def _harvest(self, amount_wei):
        before = self._get_vault_state()

        self.step_count += 1
        print(f"\n--- Step {self.step_count}: HARVEST ---")
        print(f"Harvesting {amount_wei / 10**18:,.2f} crvUSD")
        print(
            f"Vault state before: totalAssets={before.total_assets / 10**18:,.2f}, locked={before.locked_shares / 10**18:,.2f}"
        )

        if before.locked_shares > 0:
            remaining_time = max(
                0,
                self.mock_vault.full_profit_unlock_date() - boa.env.timestamp,
            )
            print(f"Existing stream: {remaining_time}s remaining")

        exp = self.mock_vault.convertToShares(amount_wei)

        with boa.env.prank(self.harvest_caller):
            self.mock_vault.harvest(
                self.harvest_caller, amount_wei, [], b"", b"", b""
            )

            after = self._get_vault_state()

            if before.ext_total_supply > 0:
                assert after.price_per_share == pytest.approx(
                    before.price_per_share, rel=1e-5
                )

            delta_locked = after.locked_shares - before.locked_shares
            assert delta_locked == pytest.approx(exp, abs=1)

            self._harvested = True

            print("New vault state:")
            print(
                f"  totalAssets: {after.total_assets / 10**18:,.2f} (change: {(after.total_assets - before.total_assets) / 10**18:,.2f})"
            )
            print(
                f"  locked: {after.locked_shares / 10**18:,.2f} (change: {delta_locked / 10**18:,.2f})"
            )
            print(f"  unlocked: {after.unlocked_shares / 10**18:,.2f}")
            print(
                f"  unlock_date: {self.mock_vault.full_profit_unlock_date()}"
            )

    def _donate(self, amount_wei):
        vault_state_before = self._get_vault_state()

        self.step_count += 1
        print(f"\n--- Step {self.step_count}: DONATE ---")
        print(
            f"Donating {amount_wei / 10**18:,.2f} crvUSD directly to strategy"
        )
        print(
            f"Vault state before: totalAssets={vault_state_before.total_assets / 10**18:,.2f}, PPS={vault_state_before.price_per_share / 10**18:,.6f}"
        )

        with boa.env.prank(self.crvusd_minter):
            self.crvusd_token.mint(
                self.mock_strategy_contract.address, amount_wei
            )

        vault_state_after = self._get_vault_state()

        print("New vault state:")
        print(
            f"  totalAssets: {vault_state_after.total_assets / 10**18:,.2f} (change: {(vault_state_after.total_assets - vault_state_before.total_assets) / 10**18:,.2f})"
        )
        print(
            f"  PPS: {vault_state_after.price_per_share / 10**18:,.6f} (change: {(vault_state_after.price_per_share - vault_state_before.price_per_share) / 10**18:,.6f})"
        )

        if vault_state_before.ext_total_supply > 0:
            assert (
                vault_state_after.price_per_share
                >= vault_state_before.price_per_share
            ), f"Donation should increase PPS: {vault_state_before.price_per_share / 10**18:.6f} -> {vault_state_after.price_per_share / 10**18:.6f}"
        else:
            assert vault_state_after.price_per_share == 10**18

        assert (
            vault_state_after.ext_total_supply
            == vault_state_before.ext_total_supply
        )

    @rule(dt=time_advance)
    def time_travel(self, dt):
        if self._get_vault_state().locked_shares == 0:
            return  # No streaming to test

        vault_state_before = self._get_vault_state()

        self.step_count += 1
        print(f"\n--- Step {self.step_count}: TIME_TRAVEL ---")
        print(f"Advancing time by {dt:,} seconds ({dt/3600:.1f} hours)")
        print(
            f"Before: locked={vault_state_before.locked_shares / 10**18:,.2f}, unlocked={vault_state_before.unlocked_shares / 10**18:,.2f}"
        )

        boa.env.time_travel(dt)

        vault_state_after = self._get_vault_state()
        print(
            f"After: locked={vault_state_after.locked_shares / 10**18:,.2f}, unlocked={vault_state_after.unlocked_shares / 10**18:,.2f}"
        )
        print(
            f"Streaming progress: {(vault_state_after.unlocked_shares - vault_state_before.unlocked_shares) / 10**18:,.2f} shares unlocked"
        )

    @invariant()
    def check_strategy_balance(self):
        vault_balance = self.crvusd_token.balanceOf(self.mock_vault.address)
        assert (
            vault_balance == 0
        ), f"Vault has stray balance: {vault_balance / 10**18:,.2f}"

    @invariant()
    def check_streaming_accounting(self):
        state = self._get_vault_state()

        assert (
            state.locked_shares >= 0
        ), f"locked_shares negative: {state.locked_shares}"

        user_sum = sum(self.mock_vault.balanceOf(u) for u in self.accounts)
        assert (
            state.ext_total_supply == user_sum + state.locked_shares
        ), f"External supply mismatch: ext_total={state.ext_total_supply}, users+locked={user_sum + state.locked_shares}"

        expected_unlocked = state.raw_vault_balance - state.locked_shares
        assert state.unlocked_shares == pytest.approx(
            expected_unlocked, abs=1
        ), f"Unlocked calculation wrong: {state.unlocked_shares} != {expected_unlocked}"

    @invariant()
    def check_erc4626_conversions(self):
        # check ERC-4626 converrsion reciprocity and monotonicity
        if self._get_vault_state().ext_total_supply == 0:
            return

        test_amounts = [1000 * 10**18, 10000 * 10**18]

        for amount in test_amounts:
            shares = self.mock_vault.convertToShares(amount)
            assert self.mock_vault.previewDeposit(amount) == shares

            back_to_assets = self.mock_vault.convertToAssets(shares)
            assert back_to_assets == pytest.approx(
                amount, rel=1e-5
            ), f"Asset conversion reciprocity failed: {amount} -> {shares} -> {back_to_assets}"
            assert (
                back_to_assets <= amount
            ), f"Asset round-trip gives user profit: {amount} -> {shares} -> {back_to_assets}"

            assets = self.mock_vault.convertToAssets(shares)
            back_to_shares = self.mock_vault.convertToShares(assets)
            assert (
                back_to_shares <= shares
            ), f"Share round-trip gives user profit: {shares} -> {assets} -> {back_to_shares}"
            assert back_to_shares == pytest.approx(
                shares, rel=1e-5
            ), f"Share conversion reciprocity failed: {shares} -> {assets} -> {back_to_shares}"

        a1, a2 = 1_000 * 10**18, 10_000 * 10**18
        assert self.mock_vault.convertToShares(
            a2
        ) >= self.mock_vault.convertToShares(
            a1
        ), f"Conversion monotonicity failed: convertToShares({a2}) < convertToShares({a1})"
        assert self.mock_vault.convertToAssets(
            a2
        ) >= self.mock_vault.convertToAssets(
            a1
        ), f"Conversion monotonicity failed: convertToAssets({a2}) < convertToAssets({a1})"

    @invariant()
    def check_price_effects(self):
        current_state = self._get_vault_state()

        if (
            self.last_state is not None
            and current_state.ext_total_supply > 0
            and self.last_state.ext_total_supply > 0
        ):
            if (
                current_state.total_assets == self.last_state.total_assets
                and current_state.locked_shares > 0
            ):
                assert (
                    current_state.price_per_share
                    >= self.last_state.price_per_share - 1
                ), f"PPS decreased during streaming: {self.last_state.price_per_share / 10**18:.6f} -> {current_state.price_per_share / 10**18:.6f}"

        self.last_state = current_state

    @invariant()
    def check_rate_consistency(self):
        state = self._get_vault_state()

        if state.locked_shares > 0:
            unlock_date = self.mock_vault.full_profit_unlock_date()
            unlock_rate = self.mock_vault.profit_unlocking_rate()
            current_time = boa.env.timestamp

            if current_time < unlock_date:
                remaining_time = unlock_date - current_time
                scale = self.mock_vault.unlock_scale()
                expected_locked = unlock_rate * remaining_time // scale

                tolerance = max(state.locked_shares // 1000, 1)
                assert expected_locked == pytest.approx(
                    state.locked_shares, abs=tolerance
                ), f"Rate consistency failed: expected_locked={expected_locked}, actual_locked={state.locked_shares}"

    @invariant()
    def check_streaming_monotonicity(self):
        current_state = self._get_vault_state()

        if getattr(self, "_harvested", False):
            self._harvested = False
            self._last_stream = current_state
            return

        if hasattr(self, "_last_stream") and self._last_stream is not None:
            prev_state = self._last_stream
            assert (
                current_state.locked_shares <= prev_state.locked_shares + 1
            ), f"Locked shares increased: {prev_state.locked_shares} -> {current_state.locked_shares}"
            assert (
                current_state.unlocked_shares >= prev_state.unlocked_shares - 1
            ), f"Unlocked shares decreased: {prev_state.unlocked_shares} -> {current_state.unlocked_shares}"

        self._last_stream = current_state

    @invariant()
    def check_preview_action_parity(self):
        s = self._get_vault_state()
        if s.ext_total_supply == 0:
            return
        a = 7_777 * 10**18
        sh = self.mock_vault.convertToShares(a)
        redeem_result = self.mock_vault.previewRedeem(sh)

        assert self.mock_vault.previewDeposit(a) == sh
        assert redeem_result == pytest.approx(a, rel=1e-5)
        assert redeem_result <= a
        assert self.mock_vault.previewMint(
            sh
        ) >= self.mock_vault.convertToAssets(sh)
        assert self.mock_vault.previewWithdraw(a) >= sh

    @rule(uid=user_id, amount=deposit_amount)
    def parity_mint(self, uid, amount):
        user = self.accounts[uid]
        sh = amount * 10**18

        max_mint = self.mock_vault.maxMint(user)
        if sh > max_mint:
            sh = max_mint

        if sh == 0:
            return

        req_preview = self.mock_vault.previewMint(sh)
        user_balance = self.crvusd_token.balanceOf(user)

        if req_preview > user_balance:
            return

        with boa.env.prank(user):
            req = self.mock_vault.previewMint(sh)
            got = self.mock_vault.mint(sh, user)
        assert got == pytest.approx(req, rel=1e-5)

    @rule(frac=withdraw_fraction, uid=user_id)
    def parity_withdraw(self, frac, uid):
        user = self.accounts[uid]
        bal = self.mock_vault.balanceOf(user)
        if bal == 0:
            return
        f = Fraction(frac).limit_denominator(10**12)
        sh = bal * f.numerator // f.denominator
        a = self.mock_vault.previewRedeem(sh)
        with boa.env.prank(user):
            got = self.mock_vault.redeem(sh, user, user)
        assert got == pytest.approx(a, rel=1e-5)

    @invariant()
    def check_max_bounds(self):
        for u in self.accounts[:3]:
            assert self.mock_vault.maxWithdraw(
                u
            ) == self.mock_vault.previewRedeem(self.mock_vault.maxRedeem(u))

    @invariant()
    def zero_identities(self):
        assert self.mock_vault.convertToShares(0) == 0
        assert self.mock_vault.convertToAssets(0) == 0
        assert self.mock_vault.previewDeposit(0) == 0
        assert self.mock_vault.previewMint(0) == 0
        assert self.mock_vault.previewWithdraw(0) == 0
        assert self.mock_vault.previewRedeem(0) == 0

    @invariant()
    def full_unlock_boundary(self):
        s = self._get_vault_state()
        if (
            boa.env.timestamp >= self.mock_vault.full_profit_unlock_date()
            and s.raw_vault_balance > 0
        ):
            assert s.locked_shares == 0
            assert s.unlocked_shares == s.raw_vault_balance

    @invariant()
    def check_no_streaming_when_disabled(self):
        if self.mock_vault.profit_max_unlock_time() == 0:
            s = self._get_vault_state()
            assert s.locked_shares == 0
            assert s.unlocked_shares == 0
            assert s.ext_total_supply == s.raw_total_supply

    @invariant()
    def total_assets_matches_strategy(self):
        assert self.mock_vault.totalAssets() == pytest.approx(
            self.mock_strategy_contract.total_assets(), abs=1
        )

    @invariant()
    def supply_conservation(self):
        s = self._get_vault_state()
        user_sum = 0
        for u in self.accounts:
            user_sum += self.mock_vault.balanceOf(u)
        assert user_sum + s.raw_vault_balance == s.raw_total_supply


def test_stateful_vault(
    mock_vault,
    mock_strategy_contract,
    funded_mock_vault_users,
    harvest_caller,
    crvusd_token,
    crvusd_minter,
):
    StatefulVault.TestCase.settings = settings(
        max_examples=50,
        stateful_step_count=50,
        deadline=120000,
    )

    StatefulVault.mock_vault = mock_vault
    StatefulVault.mock_strategy_contract = mock_strategy_contract
    StatefulVault.harvest_caller = harvest_caller
    StatefulVault.crvusd_token = crvusd_token
    StatefulVault.crvusd_minter = crvusd_minter
    StatefulVault.accounts = funded_mock_vault_users

    print(f"\n{'='*60}")
    print(f"Vault: {mock_vault.address}")
    print(f"Strategy: {mock_strategy_contract.address}")
    print(f"Users: {len(funded_mock_vault_users)}")
    print(f"{'='*60}")

    run_state_machine_as_test(StatefulVault)

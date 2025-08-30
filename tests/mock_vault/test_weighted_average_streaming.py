import boa
import pytest


def test_weighted_average_profit_locking(
    mock_vault,
    mock_strategy_contract,
    funded_mock_vault_users,
    harvest_caller,
    crvusd_token,
):
    user1 = funded_mock_vault_users[0]

    deposit_amount = int(200_000 * 1e18)

    with boa.env.prank(user1):
        shares1 = mock_vault.deposit(deposit_amount, user1)

    print("Initial setup:")
    print(f"User1 deposit: {deposit_amount / 1e18:.1f}")
    print(f"User1 shares: {shares1 / 1e18:.1f}")

    streaming_period = mock_vault.profit_max_unlock_time()
    print(f"Streaming period: {streaming_period} seconds")

    first_harvest = int(50_000 * 1e18)
    expected_locked_shares_1 = mock_vault.convertToShares(first_harvest)

    with boa.env.prank(harvest_caller):
        mock_vault.harvest(harvest_caller, first_harvest, [], b"", b"", b"")

    print(f"\nAfter first harvest ({first_harvest / 1e18:.1f}):")
    print(f"Expected locked shares: {expected_locked_shares_1 / 1e18:.1f}")
    print(
        f"Actual locked shares: {mock_vault.balanceOf(mock_vault.address) / 1e18:.1f}"
    )
    print(f"Unlocked shares: {mock_vault.unlocked_shares() / 1e18:.1f}")
    print(f"Full profit unlock date: {mock_vault.full_profit_unlock_date()}")

    first_unlock_date = mock_vault.full_profit_unlock_date()

    boa.env.time_travel(seconds=streaming_period // 3)

    print(f"\nAfter {streaming_period // 3} seconds (1/3 of period):")
    remaining_time_1 = first_unlock_date - boa.env.timestamp
    print(f"Remaining time for first harvest: {remaining_time_1} seconds")
    print(f"Unlocked shares: {mock_vault.unlocked_shares() / 1e18:.1f}")
    print(
        f"Locked shares: {mock_vault.balanceOf(mock_vault.address) / 1e18:.1f}"
    )

    second_harvest = int(30_000 * 1e18)
    expected_locked_shares_2 = mock_vault.convertToShares(second_harvest)

    existing_locked_shares = mock_vault.balanceOf(mock_vault.address)
    previously_locked_time = remaining_time_1 * existing_locked_shares
    total_locked_shares = existing_locked_shares + expected_locked_shares_2

    expected_new_period = (
        previously_locked_time + expected_locked_shares_2 * streaming_period
    ) // total_locked_shares
    expected_new_unlock_date = boa.env.timestamp + expected_new_period

    print(f"\nBefore second harvest ({second_harvest / 1e18:.1f}):")
    print(f"Existing locked shares: {existing_locked_shares / 1e18:.1f}")
    print(f"Expected new locked shares: {expected_locked_shares_2 / 1e18:.1f}")
    print(f"Previously locked time: {previously_locked_time}")
    print(f"Expected weighted average period: {expected_new_period} seconds")
    print(f"Expected new unlock date: {expected_new_unlock_date}")

    with boa.env.prank(harvest_caller):
        mock_vault.harvest(harvest_caller, second_harvest, [], b"", b"", b"")

    actual_unlock_date = mock_vault.full_profit_unlock_date()
    actual_locked_shares = mock_vault.balanceOf(mock_vault.address)

    print("\nAfter second harvest:")
    print(f"Expected total locked shares: {total_locked_shares / 1e18:.1f}")
    print(f"Actual total locked shares: {actual_locked_shares / 1e18:.1f}")
    print(f"Expected unlock date: {expected_new_unlock_date}")
    print(f"Actual unlock date: {actual_unlock_date}")
    print(
        f"Difference in unlock dates: {actual_unlock_date - expected_new_unlock_date} seconds"
    )
    print(f"Unlocked shares: {mock_vault.unlocked_shares() / 1e18:.1f}")

    time_to_half_unlock = (actual_unlock_date - boa.env.timestamp) // 2
    boa.env.time_travel(seconds=time_to_half_unlock)

    print(f"\nAfter {time_to_half_unlock} seconds (half of new period):")
    print(f"Unlocked shares: {mock_vault.unlocked_shares() / 1e18:.1f}")
    print(
        f"Locked shares: {mock_vault.balanceOf(mock_vault.address) / 1e18:.1f}"
    )

    expected_unlocked_at_half = actual_locked_shares // 2
    actual_unlocked_at_half = mock_vault.unlocked_shares()

    print(f"Expected unlocked at half: {expected_unlocked_at_half / 1e18:.1f}")
    print(f"Actual unlocked at half: {actual_unlocked_at_half / 1e18:.1f}")

    user_withdrawable = mock_vault.maxWithdraw(user1)
    expected_withdrawable = (
        shares1 * mock_vault.totalAssets() // mock_vault.totalSupply()
    )

    print(f"User1 withdrawable: {user_withdrawable / 1e18:.2f}")
    print(f"Expected withdrawable: {expected_withdrawable / 1e18:.2f}")

    boa.env.time_travel(seconds=time_to_half_unlock)

    print("\nAt end of weighted average period:")
    print(f"Unlocked shares: {mock_vault.unlocked_shares() / 1e18:.1f}")
    print(
        f"Locked shares: {mock_vault.balanceOf(mock_vault.address) / 1e18:.1f}"
    )

    total_expected_profit = first_harvest + second_harvest
    final_withdrawable = mock_vault.maxWithdraw(user1)
    total_expected_final = deposit_amount + total_expected_profit

    print(f"Total expected profit: {total_expected_profit / 1e18:.1f}")
    print(f"Expected final withdrawable: {total_expected_final / 1e18:.1f}")
    print(f"Actual final withdrawable: {final_withdrawable / 1e18:.1f}")

    assert actual_unlock_date == pytest.approx(expected_new_unlock_date, abs=2)
    assert mock_vault.balanceOf(mock_vault.address) == 0
    assert final_withdrawable == pytest.approx(total_expected_final, rel=1e-3)

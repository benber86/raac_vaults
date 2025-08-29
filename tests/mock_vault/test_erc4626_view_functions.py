import boa
import pytest
from tabulate import tabulate


def test_view_functions_empty_vault(mock_vault, crvusd_token):

    # asset() returns the address of the deposited token
    assert mock_vault.asset() == crvusd_token.address

    # totalAssets() shows total managed assets
    assert mock_vault.totalAssets() == 0

    # convertToShares/convertToAssets has price of 1 if supply is 0, does not revert
    assert mock_vault.convertToShares(1000) == 1000
    assert mock_vault.convertToAssets(1000) == 1000
    assert mock_vault.convertToShares(0) == 0
    assert mock_vault.convertToAssets(0) == 0

    # maxDeposit/maxMint never revert, should return 2**256-1 when no limit
    max_uint256 = 2**256 - 1
    assert mock_vault.maxDeposit(boa.env.generate_address()) == max_uint256
    assert mock_vault.maxMint(boa.env.generate_address()) == max_uint256

    # maxWithdraw/maxRedeem does not revert
    user = boa.env.generate_address()
    assert mock_vault.maxWithdraw(user) == 0
    assert mock_vault.maxRedeem(user) == 0

    # previewDeposit/previewMint has price of 1 if supply is 0, does not revert
    assert mock_vault.previewDeposit(1000) == 1000
    assert mock_vault.previewMint(1000) == 1000
    assert mock_vault.previewDeposit(0) == 0
    assert mock_vault.previewMint(0) == 0

    # previewWithdraw/previewRedeem does not revert
    assert mock_vault.previewWithdraw(1000) == 1000
    assert mock_vault.previewRedeem(1000) == 1000
    assert mock_vault.previewWithdraw(0) == 0
    assert mock_vault.previewRedeem(0) == 0

    # Edge case: large numbers shouldn't revert
    assert mock_vault.convertToShares(max_uint256) == max_uint256
    assert mock_vault.convertToAssets(max_uint256) == max_uint256
    assert mock_vault.previewDeposit(max_uint256) == max_uint256
    assert mock_vault.previewMint(max_uint256) == max_uint256


def test_view_functions_after_single_deposit(
    mock_vault, funded_mock_vault_users, crvusd_token
):
    vault = mock_vault
    user = funded_mock_vault_users[0]
    deposit_amount = int(100_000 * 1e18)

    # User deposits
    with boa.env.prank(user):
        shares = vault.deposit(deposit_amount, user)

    # totalAssets() reflects the deposit
    assert vault.totalAssets() == deposit_amount

    # convertToShares/convertToAssets with 1:1 ratio
    assert vault.convertToShares(deposit_amount) == shares
    assert vault.convertToAssets(shares) == deposit_amount
    assert vault.convertToShares(0) == 0
    assert vault.convertToAssets(0) == 0

    # maxDeposit/maxMint unlimited
    max_uint256 = 2**256 - 1
    assert vault.maxDeposit(user) == max_uint256
    assert vault.maxMint(user) == max_uint256

    # maxWithdraw/maxRedeem for depositor
    assert vault.maxWithdraw(user) == deposit_amount
    assert vault.maxRedeem(user) == shares

    # maxWithdraw/maxRedeem for non-depositor
    other_user = funded_mock_vault_users[1]
    assert vault.maxWithdraw(other_user) == 0
    assert vault.maxRedeem(other_user) == 0

    # previewDeposit/previewMint consistent
    test_amount = int(50_000 * 1e18)
    assert vault.previewDeposit(test_amount) == test_amount
    assert vault.previewMint(test_amount) == test_amount

    # previewWithdraw/previewRedeem consistent
    assert vault.previewWithdraw(test_amount) == test_amount
    assert vault.previewRedeem(test_amount) == test_amount


@pytest.mark.parametrize("donation_amount", [int(100 * 1e18), int(600 * 1e18)])
def test_view_functions_after_donation(
    mock_vault,
    mock_strategy_contract,
    funded_mock_vault_users,
    crvusd_token,
    donation_amount,
):

    user = funded_mock_vault_users[0]
    deposit_amount = int(1000 * 1e18)

    # User deposits first
    with boa.env.prank(user):
        mock_vault.deposit(deposit_amount, user)

    print(
        f"Mock vault balance after deposit: {crvusd_token.balanceOf(mock_vault.address)}"
    )
    print(
        f"Mock strategy balance after deposit: {crvusd_token.balanceOf(mock_strategy_contract.address)}"
    )

    # Direct donation to strategy (simulating yield)
    donor = funded_mock_vault_users[1]
    with boa.env.prank(donor):
        crvusd_token.transfer(mock_strategy_contract.address, donation_amount)

    print(
        f"Mock vault balance after donation: {crvusd_token.balanceOf(mock_vault.address)}"
    )
    print(
        f"Mock strategy balance after donation: {crvusd_token.balanceOf(mock_strategy_contract.address)}"
    )

    # Get current state
    total_assets = mock_vault.totalAssets()
    total_supply = mock_vault.totalSupply()
    user_shares = mock_vault.balanceOf(user)

    print(f"\n=== Donation Test: {donation_amount / 1e18:.1f} ===")
    print(f"Total Assets: {total_assets / 1e18:.1f}")
    print(f"Total Supply: {total_supply / 1e18:.1f}")
    print(f"User Shares:  {user_shares / 1e18:.1f}")
    print(f"Assets * Total Supply: {total_assets * total_supply}")

    # Test conversion functions with table - use smaller values to show rounding
    test_amounts = [7, 333, 9999]

    # convertToAssets table
    convert_assets_data = []
    for amount in test_amounts:
        expected_down = amount * total_assets // total_supply  # Round down
        expected_up = (
            amount * total_assets + total_supply - 1
        ) // total_supply  # Round up
        actual = mock_vault.convertToAssets(amount)
        wrong_up = expected_up
        convert_assets_data.append(
            [
                f"{amount}",
                f"{expected_down} (Round Down)",
                f"{actual}",
                f"{actual - expected_down}",
                f"{wrong_up} (Round Up)",
            ]
        )

    print("\n--- convertToAssets ---")
    print(
        tabulate(
            convert_assets_data,
            headers=["Shares", "Expected", "Actual", "Diff", "Wrong"],
            tablefmt="grid",
        )
    )

    # convertToShares table
    convert_shares_data = []
    for amount in test_amounts:
        expected_down = amount * total_supply // total_assets  # Round down
        expected_up = (
            amount * total_supply + total_assets - 1
        ) // total_assets  # Round up
        actual = mock_vault.convertToShares(amount)
        wrong_up = expected_up
        convert_shares_data.append(
            [
                f"{amount}",
                f"{expected_down} (Round Down)",
                f"{actual}",
                f"{actual - expected_down}",
                f"{wrong_up} (Round Up)",
            ]
        )

    print("\n--- convertToShares ---")
    print(
        tabulate(
            convert_shares_data,
            headers=["Assets", "Expected", "Actual", "Diff", "Wrong"],
            tablefmt="grid",
        )
    )

    # previewDeposit table
    preview_deposit_data = []
    for amount in test_amounts:
        expected_down = amount * total_supply // total_assets  # Round down
        expected_up = (
            amount * total_supply + total_assets - 1
        ) // total_assets  # Round up
        actual = mock_vault.previewDeposit(amount)
        wrong_up = expected_up
        preview_deposit_data.append(
            [
                f"{amount}",
                f"{expected_down} (Round Down)",
                f"{actual}",
                f"{actual - expected_down}",
                f"{wrong_up} (Round Up)",
            ]
        )

    print("\n--- previewDeposit ---")
    print(
        tabulate(
            preview_deposit_data,
            headers=["Assets", "Expected", "Actual", "Diff", "Wrong"],
            tablefmt="grid",
        )
    )

    # previewRedeem table
    preview_redeem_data = []
    for amount in test_amounts:
        expected_down = amount * total_assets // total_supply  # Round down
        expected_up = (
            amount * total_assets + total_supply - 1
        ) // total_supply  # Round up
        actual = mock_vault.previewRedeem(amount)
        wrong_up = expected_up
        preview_redeem_data.append(
            [
                f"{amount}",
                f"{expected_down} (Round Down)",
                f"{actual}",
                f"{actual - expected_down}",
                f"{wrong_up} (Round Up)",
            ]
        )

    print("\n--- previewRedeem ---")
    print(
        tabulate(
            preview_redeem_data,
            headers=["Shares", "Expected", "Actual", "Diff", "Wrong"],
            tablefmt="grid",
        )
    )

    # Basic assertions with detailed output
    expected_total = deposit_amount + donation_amount
    print("\nAssertion check:")
    print(f"Total Assets: {total_assets / 1e18:.1f}")
    print(f"Expected (Deposit + Donation): {expected_total / 1e18:.1f}")

    assert total_assets == pytest.approx(expected_total, rel=1e-6)

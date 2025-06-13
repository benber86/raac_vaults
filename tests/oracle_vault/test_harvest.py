import boa
from boa.util.abi import abi_encode
from eth_utils import function_signature_to_4byte_selector

from src import raac_vault, strategy
from src.harvesters import oracle_harvester
from tests.utils.constants import CRVUSD_INDEX_PYUSD_POOL


def test_oracle_vault_harvest_single_staker(
    test_oracle_vault,
    crvusd_token,
    funded_accounts,
    pyusd_crvusd_pool,
    get_base_reward_pool,
    harvest_manager,
):
    vault_addr, strategy_addr, harvester_addr = test_oracle_vault
    user = funded_accounts[0]

    vault_contract = raac_vault.at(vault_addr)
    strategy_contract = strategy.at(strategy_addr)
    get_base_reward_pool(strategy_contract.rewards_contract())

    user_lp_balance = pyusd_crvusd_pool.balanceOf(user)
    deposit_amount = user_lp_balance // 2

    with boa.env.prank(user):
        pyusd_crvusd_pool.approve(vault_addr, deposit_amount)
        vault_contract.deposit(deposit_amount, user)

    initial_total_assets = vault_contract.totalAssets()

    # 1 hour otherwise chainlink price feed might becomes stale
    # Note the test is flaky and will fail if there is less than 1 hour left on heartbeat
    boa.env.time_travel(seconds=3600)

    sig = "add_liquidity_with_check(address,address,uint256,uint256)"
    selector = function_signature_to_4byte_selector(sig)
    encoded_args = abi_encode(
        "(address,address,uint256,uint256)",
        [
            pyusd_crvusd_pool.address,
            crvusd_token.address,
            CRVUSD_INDEX_PYUSD_POOL,
            0,  # min_amount_out
        ],
    )
    target_hook_calldata = selector + encoded_args

    with boa.env.prank(harvest_manager):
        vault_contract.harvest(user, 0, [], b"", target_hook_calldata, b"")

    final_total_assets = vault_contract.totalAssets()
    assert final_total_assets > initial_total_assets


def test_oracle_slippage_protection(
    test_oracle_vault,
    crvusd_token,
    funded_accounts,
    pyusd_crvusd_pool,
    get_base_reward_pool,
    harvest_manager,
):
    vault_addr, strategy_addr, harvester_addr = test_oracle_vault
    user = funded_accounts[0]

    vault_contract = raac_vault.at(vault_addr)
    strategy_contract = strategy.at(strategy_addr)
    harvester_contract = oracle_harvester.at(harvester_addr)

    user_lp_balance = pyusd_crvusd_pool.balanceOf(user)
    deposit_amount = user_lp_balance // 2

    with boa.env.prank(user):
        pyusd_crvusd_pool.approve(vault_addr, deposit_amount)
        vault_contract.deposit(deposit_amount, user)

    boa.env.time_travel(seconds=3600)

    with boa.env.prank(harvest_manager):
        harvester_contract.set_slippage(9999)

    sig = "add_liquidity_with_check(address,address,uint256,uint256)"
    selector = function_signature_to_4byte_selector(sig)
    encoded_args = abi_encode(
        "(address,address,uint256,uint256)",
        [
            pyusd_crvusd_pool.address,
            crvusd_token.address,
            CRVUSD_INDEX_PYUSD_POOL,
            0,
        ],
    )
    target_hook_calldata = selector + encoded_args

    try:
        with boa.env.prank(harvest_manager):
            vault_contract.harvest(
                user, 0, [], b"", target_hook_calldata, b""
            )
    except Exception as e:
        # If it reverts, it should be due to slippage protection
        assert (
            "slippage" in str(e).lower()
            or "CVX swap slippage" in str(e)
            or "CRV swap slippage" in str(e)
        )


def test_oracle_vault_reverts_on_stale_price(
    test_oracle_vault,
    crvusd_token,
    funded_accounts,
    pyusd_crvusd_pool,
    get_base_reward_pool,
    harvest_manager,
):
    vault_addr, strategy_addr, harvester_addr = test_oracle_vault
    user = funded_accounts[0]

    vault_contract = raac_vault.at(vault_addr)
    strategy_contract = strategy.at(strategy_addr)
    harvester_contract = oracle_harvester.at(harvester_addr)

    harvester_contract.set_approvals()

    get_base_reward_pool(strategy_contract.rewards_contract())

    user_lp_balance = pyusd_crvusd_pool.balanceOf(user)
    deposit_amount = user_lp_balance // 2

    with boa.env.prank(user):
        pyusd_crvusd_pool.approve(vault_addr, deposit_amount)
        vault_contract.deposit(deposit_amount, user)

    # Time travel beyond Chainlink heartbeat (24 hours)
    boa.env.time_travel(seconds=86400 * 7)

    # Prepare target hook calldata
    sig = "add_liquidity_with_check(address,address,uint256,uint256)"
    selector = function_signature_to_4byte_selector(sig)
    encoded_args = abi_encode(
        "(address,address,uint256,uint256)",
        [
            pyusd_crvusd_pool.address,
            crvusd_token.address,
            CRVUSD_INDEX_PYUSD_POOL,
            0,
        ],
    )
    target_hook_calldata = selector + encoded_args

    # Should revert due to stale price
    with boa.env.prank(harvest_manager):
        with boa.reverts("Stale price"):
            vault_contract.harvest(
                user, 0, [], b"", target_hook_calldata, b""
            )


def test_oracle_vault_protects_against_pool_manipulation(
        test_oracle_vault,
        crvusd_token,
        pyusd_token,
        funded_accounts,
        pyusd_crvusd_pool,
        get_base_reward_pool,
        crvusd_minter,
        harvest_manager,
):
    vault_addr, strategy_addr, harvester_addr = test_oracle_vault
    user = funded_accounts[0]
    manipulator = funded_accounts[9]

    vault_contract = raac_vault.at(vault_addr)
    strategy_contract = strategy.at(strategy_addr)
    harvester_contract = oracle_harvester.at(harvester_addr)

    harvester_contract.set_approvals()

    get_base_reward_pool(strategy_contract.rewards_contract())

    user_lp_balance = pyusd_crvusd_pool.balanceOf(user)
    deposit_amount = user_lp_balance // 2

    with boa.env.prank(user):
        pyusd_crvusd_pool.approve(vault_addr, deposit_amount)
        vault_contract.deposit(deposit_amount, user)

    boa.env.time_travel(seconds=3600)  # 1 hour

    # Get pool balances before manipulation
    crvusd_balance_in_pool = crvusd_token.balanceOf(pyusd_crvusd_pool.address)
    pyusd_balance_in_pool = pyusd_token.balanceOf(pyusd_crvusd_pool.address)

    print(f"Pool crvUSD balance before: {crvusd_balance_in_pool / 1e18:.2f}")
    print(f"Pool PYUSD balance before: {pyusd_balance_in_pool / 1e6:.2f}")
    # manipulate based on PYUSD balance
    pyusd_to_drain = pyusd_balance_in_pool * 9995 // 10000

    # get quote for how much crvUSD we need
    crvusd_needed = pyusd_crvusd_pool.get_dx(1, 0, pyusd_to_drain)

    print(f"pyUSD to drain: {pyusd_to_drain / 1e6:.2f}")
    print(f"crvUSD Needed: {crvusd_needed / 1e18:.2f}")

    with boa.env.prank(crvusd_minter):
        crvusd_token.mint(manipulator, crvusd_needed * 2)

    spot_price_before = pyusd_crvusd_pool.get_dy(1, 0, 10 ** 18)  # crvUSD -> PYUSD
    oracle_price_before = pyusd_crvusd_pool.price_oracle(0)

    print(f"Spot price before manipulation (1 crvUSD -> PYUSD): {spot_price_before / 1e6:.6f}")
    print(f"Oracle price before manipulation: {oracle_price_before / 1e18:.6f}")

    # Execute manipulation
    with boa.env.prank(manipulator):
        crvusd_token.approve(pyusd_crvusd_pool.address, crvusd_needed * 2)
        pyusd_received = pyusd_crvusd_pool.exchange(
            1, 0, crvusd_needed, 0
        )

    spot_price_after = pyusd_crvusd_pool.get_dy(1, 0, 10 ** 18)
    oracle_price_after = pyusd_crvusd_pool.price_oracle(0)

    print(f"Spot price after manipulation (1 crvUSD -> PYUSD): {spot_price_after / 1e6:.6f}")
    print(f"Oracle price after manipulation: {oracle_price_after / 1e18:.6f}")

    spot_price_change = ((spot_price_after - spot_price_before) / spot_price_before * 100)
    print(f"Spot price change: {spot_price_change:.2f}%")

    crvusd_after = crvusd_token.balanceOf(pyusd_crvusd_pool.address)
    pyusd_after = pyusd_token.balanceOf(pyusd_crvusd_pool.address)
    print(f"Pool crvUSD balance after: {crvusd_after / 1e18:.2f}")
    print(f"Pool PYUSD balance after: {pyusd_after / 1e6:.2f}")

    sig = "add_liquidity_with_check(address,address,uint256,uint256)"
    selector = function_signature_to_4byte_selector(sig)
    encoded_args = abi_encode(
        "(address,address,uint256,uint256)",
        [
            pyusd_crvusd_pool.address,
            crvusd_token.address,
            CRVUSD_INDEX_PYUSD_POOL,
            0,
        ],
    )
    target_hook_calldata = selector + encoded_args

    # should revert due to oracle protection detecting manipulation
    with boa.env.prank(harvest_manager):
        with boa.reverts():
            vault_contract.harvest(
                user, 0, [], b"", target_hook_calldata, b""
            )

    # undo the manipulation and show harvest works normally
    with boa.env.prank(manipulator):
        pyusd_token.approve(pyusd_crvusd_pool.address, pyusd_received)
        pyusd_crvusd_pool.exchange(0, 1, pyusd_received * 95 // 100, 0)
    with boa.env.prank(harvest_manager):
        vault_contract.harvest(user, 0, [], b"", target_hook_calldata, b"")

    final_total_assets = vault_contract.totalAssets()
    assert final_total_assets > deposit_amount, "Harvest should have succeeded after manipulation was undone"
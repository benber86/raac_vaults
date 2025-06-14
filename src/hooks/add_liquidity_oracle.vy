# pragma version ^0.4.1
"""
@title RAAC Vault hook to add one-sided liquidity with oracle protection
@custom:contract-name raac_add_liquidity_oracle_hook
@license MIT
@author benny
"""

from ethereum.ercs import IERC20
from ..modules import constants
from ..interfaces import ICurveStableSwapNG
from ..interfaces import IHarvester

MAX_COINS: constant(uint256) = 8
CRVUSD_CHAINLINK_FEED: constant(address) = 0xEEf0C605546958c1f899b6fB336C20671f9cD49F
CHAINLINK_DECIMALS: constant(uint256) = 8
CHAINLINK_HEARTBEAT: constant(uint256) = 86400  # 24 hours


interface IChainlinkFeed:
    def latestRoundData() -> (uint80, int256, uint256, uint256, uint80): view


@internal
@view
def _get_crvusd_price() -> uint256:
    """
    @notice Get crvUSD price from Chainlink oracle
    @return Price of crvUSD in USD with 18 decimals
    """
    round_id: uint80 = 0
    price: int256 = 0
    started_at: uint256 = 0
    updated_at: uint256 = 0
    answered_in_round: uint80 = 0

    (round_id, price, started_at, updated_at, answered_in_round) = staticcall IChainlinkFeed(
        CRVUSD_CHAINLINK_FEED
    ).latestRoundData()

    assert updated_at >= block.timestamp - CHAINLINK_HEARTBEAT, "Stale price"
    assert price > 0, "Invalid price"

    # Convert from 8 decimals to 18 decimals
    return convert(price, uint256) * 10**(18 - CHAINLINK_DECIMALS)


@internal
@view
def _calc_lp_token_price(
    _pool: address,
    _crvusd_price: uint256,
    _crvusd_index: uint256,
) -> uint256:
    """
    @notice Calculate LP token price using virtual price and coin oracles
    @param _pool The Curve pool address
    @param _crvusd_index Index of crvUSD in the pool (0 or 1)
    @param _n_coins Number of coins in the pool
    @return LP token price in USD with 18 decimals
    @dev For stableswap pools: LP price floor = virtual_price * min(coin prices in USD)
    """
    virtual_price: uint256 = staticcall ICurveStableSwapNG(_pool).get_virtual_price()
    # to be safe we ensure that the pool is a 2 asset pool
    assert staticcall ICurveStableSwapNG(_pool).N_COINS() == 2

    # Get the pool's price oracle
    # price_oracle(0) always returns price of coin1 in terms of coin0
    price_oracle: uint256 = staticcall ICurveStableSwapNG(_pool).price_oracle(0)

    if _crvusd_index == 0:
        # crvUSD is coin0, so price_oracle gives us coin1 price in crvUSD
        # To get coin1 price in USD: multiply by crvUSD price
        other_price_usd: uint256 = (price_oracle * _crvusd_price) // 10**18
    else:
        # crvUSD is coin1, so price_oracle gives us crvUSD price in coin0
        # To get coin0 price in USD: invert the ratio and multiply by crvUSD price
        # coin0_price_usd = crvusd_price / price_oracle
        other_price_usd: uint256 = (_crvusd_price * 10**18) // price_oracle

    min_price: uint256 = _crvusd_price if _crvusd_price < other_price_usd else other_price_usd

    # LP token price = virtual_price * min(coin prices)
    return (virtual_price * min_price) // 10**18


@external
def add_liquidity_with_check(
    _pool_address: address,
    _token: address,
    _token_index: uint256,
    _min_amount_out: uint256,
):
    """
    @notice Add one-sided liquidity with oracle-based sandwich protection
    @param _pool_address The Curve NG pool contract address
    @param _token The token address to provide as liquidity (crvUSD)
    @param _token_index The index of the token in the pool (crvUSD)
    @param _min_amount_out If user specified a min_amount_out and it's higher
            than our slippage floor, we will use that
    @dev Validates LP token value using oracle prices to prevent sandwiching
    """
    amount: uint256 = staticcall IERC20(_token).balanceOf(msg.sender)
    if amount == 0:
        return

    extcall IHarvester(msg.sender).transfer_to_target_hook(_token, amount)
    allowed_slippage: uint256 = staticcall IHarvester(msg.sender).allowed_slippage()
    # Approve pool
    extcall IERC20(_token).approve(_pool_address, 0)
    extcall IERC20(_token).approve(_pool_address, amount)

    # Calculate expected LP tokens based on oracle prices
    # For single-sided deposits, expected = deposit_value / lp_token_price
    crvusd_price: uint256 = self._get_crvusd_price()
    lp_price: uint256 = self._calc_lp_token_price(_pool_address, crvusd_price, _token_index)

    # Value of deposit in USD
    deposit_value_usd: uint256 = (amount * crvusd_price) // 10**18

    # Expected LP tokens
    expected_lp_tokens: uint256 = (deposit_value_usd * 10**18) // lp_price
    min_lp_with_slippage: uint256 = (expected_lp_tokens * allowed_slippage) // constants.DECIMALS
    # We take the highest min amount out
    final_slippage_amount: uint256 = max(min_lp_with_slippage, _min_amount_out)

    # Prepare amounts array
    liquidity_amounts: DynArray[uint256, MAX_COINS] = empty(DynArray[uint256, MAX_COINS])
    for i: uint256 in range(MAX_COINS):
        if i == _token_index:
            liquidity_amounts.append(amount)
            break
        liquidity_amounts.append(0)

    extcall ICurveStableSwapNG(_pool_address).add_liquidity(
        liquidity_amounts, final_slippage_amount, msg.sender
    )

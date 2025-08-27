# pragma version 0.4.3
# @license MIT

"""
@title RAAC Curve Swapper Module
@author RAAC
@notice Swaps CRV and CVX rewards to crvUSD using Curve pools for RAAC harvesters
@dev This module handles the reward token swapping process for Curve-based harvesting.
     It swaps CVX tokens to ETH via CVX/ETH pool, CRV tokens to ETH via TriCrypto pool,
     then converts the accumulated ETH to crvUSD via TriCrypto pool. The module includes
     hooks for handling extra reward tokens and target asset conversion. All swaps use
     minimal slippage protection as the final slippage check occurs at the target asset level.
"""

from ethereum.ercs import IERC20
from src.interfaces import ICurveV2Pool
from src.interfaces import ICurveTriCryptoFactoryNG
from src.interfaces import IStrategy
from src.modules import constants
from src.modules.swappers import swapper

initializes: swapper

exports: (
    swapper.extra_reward_hook,
    swapper.factory,
    swapper.set_extra_reward_hook,
    swapper.set_strategy,
    swapper.set_target_hook,
    swapper.strategy,
    swapper.target_hook,
    swapper.transfer_to_reward_hook,
    swapper.transfer_to_target_hook,
    swapper.treasury,
    swapper.forward_tokens,
    swapper.__default__,
)


@deploy
def __init__(_factory: address):
    swapper.__init__(_factory)


@external
def set_approvals():
    """
    @notice Set token approvals for Curve pools to enable swapping
    @dev Approves CVX for CVX/ETH pool and CRV for TriCrypto pool
    """
    # CVX -> ETH
    extcall IERC20(constants.CVX_TOKEN).approve(constants.CURVE_CVX_ETH_POOL, 0)
    extcall IERC20(constants.CVX_TOKEN).approve(constants.CURVE_CVX_ETH_POOL, max_value(uint256))

    # CRV -> ETH
    extcall IERC20(constants.CRV_TOKEN).approve(constants.CURVE_TRICRV_POOL, 0)
    extcall IERC20(constants.CRV_TOKEN).approve(constants.CURVE_TRICRV_POOL, max_value(uint256))


@internal
def _cvx_to_eth(_amount: uint256, _min_amount_out: uint256) -> uint256:
    """
    @notice Swap CVX tokens to ETH using Curve CVX/ETH pool
    @param _amount Amount of CVX tokens to swap
    @param _min_amount_out Minimum ETH amount expected (slippage protection)
    @return Amount of ETH received from the swap
    """
    if _amount == 0:
        return 0
    return extcall ICurveV2Pool(constants.CURVE_CVX_ETH_POOL).exchange_underlying(
        1, 0, _amount, _min_amount_out
    )


@internal
def _crv_to_eth(_amount: uint256, _min_amount_out: uint256) -> uint256:
    """
    @notice Swap CRV tokens to ETH using Curve TriCrypto pool
    @param _amount Amount of CRV tokens to swap
    @param _min_amount_out Minimum ETH amount expected (slippage protection)
    @return Amount of ETH received from the swap
    """
    if _amount == 0:
        return 0
    return extcall ICurveTriCryptoFactoryNG(constants.CURVE_TRICRV_POOL).exchange(
        2, 1, _amount, _min_amount_out, True
    )


@internal
def _eth_to_crvusd(_amount: uint256, _min_amount_out: uint256) -> uint256:
    """
    @notice Swap ETH to crvUSD using Curve TriCrypto pool
    @param _amount Amount of ETH to swap (in wei)
    @param _min_amount_out Minimum crvUSD amount expected (slippage protection)
    @return Amount of crvUSD received from the swap
    """
    if _amount == 0:
        return 0
    return extcall ICurveTriCryptoFactoryNG(constants.CURVE_TRICRV_POOL).exchange(
        1, 0, _amount, _min_amount_out, True, value=_amount
    )


@internal
def _swap_rewards_to_eth() -> uint256:
    cvx_balance: uint256 = staticcall IERC20(constants.CVX_TOKEN).balanceOf(self)
    crv_balance: uint256 = staticcall IERC20(constants.CRV_TOKEN).balanceOf(self)
    eth_from_crv: uint256 = 0
    eth_from_cvx: uint256 = 0
    # min_amounts_out are set to 1 as slippage check is done on the final crvUSD amount
    if cvx_balance > 0:
        eth_from_cvx = self._cvx_to_eth(cvx_balance, 1)
    if crv_balance > 0:
        eth_from_crv = self._crv_to_eth(crv_balance, 1)

    return eth_from_cvx + eth_from_crv


@internal
def _swap(
    _caller: address,
    _min_amount_out: uint256,
    _reward_hook_calldata: Bytes[4096],
    _target_hook_calldata: Bytes[4096],
) -> uint256:
    """
    @notice Swap accumulated CRV and CVX rewards to crvUSD
    @param _caller Address to receive caller fee
    @param _min_amount_out Minimum amount expected from final swap to target asset
    @param _reward_hook_calldata Calldata to pass to extra reward hook contract
    @param _target_hook_calldata Calldata to pass to target hook contract
    @return target_asset_balance Amount of target asset received
    """
    self._swap_rewards_to_eth()

    # if a hook contract is set to handle extra rewards, we call it
    if swapper.extra_reward_hook != empty(address):
        raw_call(
            swapper.extra_reward_hook,
            _reward_hook_calldata,
            value=0,
        )

    crvusd_received: uint256 = self._eth_to_crvusd(self.balance, 1)

    # Pay the platform fee in crvUSD to the treasury
    platform_fee: uint256 = staticcall IStrategy(swapper.strategy).platform_fee()
    treasury: address = swapper._treasury()
    swapper._collect_fee(treasury, constants.CRVUSD_TOKEN, crvusd_received, platform_fee)

    # Pay the caller incentive in crvUSD
    caller_fee: uint256 = staticcall IStrategy(swapper.strategy).caller_fee()
    swapper._collect_fee(_caller, constants.CRVUSD_TOKEN, crvusd_received, caller_fee)

    # if we have a hook contract to handle further operations
    if swapper.target_hook != empty(address):
        raw_call(
            swapper.target_hook,
            _target_hook_calldata,
            value=0,
        )

    target_asset: address = staticcall IStrategy(swapper.strategy).asset()
    target_asset_balance: uint256 = staticcall IERC20(target_asset).balanceOf(self)
    assert target_asset_balance > _min_amount_out, "Slippage"
    assert extcall IERC20(target_asset).transfer(
        swapper.strategy,
        target_asset_balance,
        default_return_value=True,
    )
    return target_asset_balance

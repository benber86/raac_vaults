# pragma version ^0.4.1
# @license MIT

from ethereum.ercs import IERC20
from ..interfaces import ICurveV2Pool
from ..interfaces import ICurveTriCryptoFactoryNG
from ..interfaces import IStrategy
from . import constants
from . import swapper

initializes: swapper

exports: swapper.__interface__


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

    # Pay the caller incentive in crvUSD
    swapper._pay_out_caller_fee(_caller, constants.CRVUSD_TOKEN, crvusd_received)

    # if we have a hook contract to handle further operations
    if swapper.target_hook != empty(address):
        raw_call(
            swapper.target_hook,
            _target_hook_calldata,
            value=0,
        )

    target_asset: address = staticcall IStrategy(swapper.fee_collector.strategy).asset()
    target_asset_balance: uint256 = staticcall IERC20(target_asset).balanceOf(self)
    assert target_asset_balance > _min_amount_out, "Slippage"
    assert extcall IERC20(target_asset).transfer(
        swapper.fee_collector.strategy, target_asset_balance, default_return_value=True
    )
    return target_asset_balance

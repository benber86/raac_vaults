# pragma version ^0.4.1
# @license MIT

from ethereum.ercs import IERC20
from . import swapper
from . import constants
from ..interfaces import IStrategy
from ..interfaces import ICurveV2Pool
from ..interfaces import IVault
from ..interfaces import ICurveTriCryptoFactoryNG

initializes: swapper

exports: swapper.__interface__


event SlippageUpdated:
    new_slippage: uint256


# State variables
allowed_slippage: public(uint256)


@deploy
def __init__(_factory: address):
    swapper.__init__(_factory)
    self.allowed_slippage = 9800  # 2% default slippage


@external
def set_approvals():
    """
    @notice Set token approvals for Curve pools to enable swapping
    @dev Approves CVX for CVX/ETH pool and CRV for TriCrypto pool
    """
    # CVX -> ETH
    assert extcall IERC20(constants.CVX_TOKEN).approve(
        constants.CURVE_CVX_ETH_POOL, 0, default_return_value=True
    )
    assert extcall IERC20(constants.CVX_TOKEN).approve(
        constants.CURVE_CVX_ETH_POOL, max_value(uint256), default_return_value=True
    )

    # CRV -> ETH
    assert extcall IERC20(constants.CRV_TOKEN).approve(
        constants.CURVE_TRICRV_POOL, 0, default_return_value=True
    )
    assert extcall IERC20(constants.CRV_TOKEN).approve(
        constants.CURVE_TRICRV_POOL, max_value(uint256), default_return_value=True
    )


@external
def set_slippage(_slippage: uint256):
    """
    @notice Update the allowed slippage tolerance for swaps
    @param _slippage New slippage tolerance (e.g., 9800 = 2% slippage)
    @dev Only callable by strategy contract
    @dev Slippage must be <= 10000 (100%)
    """
    vault: IVault = IVault(staticcall IStrategy(swapper.fee_collector.strategy).vault())
    assert staticcall vault.hasRole(staticcall vault.HARVESTER_ROLE(), msg.sender), "Manager only"

    assert _slippage <= constants.DECIMALS, "Invalid slippage"
    assert _slippage >= 9000, "Slippage too high"
    self.allowed_slippage = _slippage
    log SlippageUpdated(new_slippage=_slippage)


@internal
@view
def _calc_cvx_value_in_eth(_amount: uint256) -> uint256:
    """
    @notice Calculate the ETH value of CVX using Curve pool oracle
    @param _amount The amount of CVX tokens to value
    @return The equivalent value in ETH (18 decimals)
    """
    if _amount == 0:
        return 0
    cvx_eth_price: uint256 = staticcall ICurveV2Pool(constants.CURVE_CVX_ETH_POOL).price_oracle()
    return (_amount * cvx_eth_price) // 10**18


@internal
@view
def _calc_crv_value_in_eth(_amount: uint256) -> uint256:
    """
    @notice Calculate the ETH value of CRV using Curve TriCrypto pool oracle
    @param _amount The amount of CRV tokens to value
    @return The equivalent value in ETH
    @dev Uses price_oracle(1) for CRV/ETH price
    """
    if _amount == 0:
        return 0
    crv_price_numerator: uint256 = staticcall ICurveTriCryptoFactoryNG(
        constants.CURVE_TRICRV_POOL
    ).price_oracle(1)
    eth_price_numerator: uint256 = staticcall ICurveTriCryptoFactoryNG(
        constants.CURVE_TRICRV_POOL
    ).price_oracle(0)
    return (_amount * crv_price_numerator) // eth_price_numerator


@internal
@view
def _calc_eth_value_in_crvusd(_eth_amount: uint256) -> uint256:
    """
    @notice Calculate the crvUSD value of ETH using TriCrypto pool oracle
    @param _eth_amount The amount of ETH to value (in wei)
    @return The equivalent value in crvUSD
    @dev Uses price_oracle(0) which gives ETH price in crvUSD
    """
    if _eth_amount == 0:
        return 0

    eth_price_in_crvusd: uint256 = staticcall ICurveTriCryptoFactoryNG(
        constants.CURVE_TRICRV_POOL
    ).price_oracle(0)

    return (_eth_amount * eth_price_in_crvusd) // 10**18


@internal
def _cvx_to_eth(_amount: uint256, _min_amount_out: uint256) -> uint256:
    """
    @notice Swap CVX tokens to ETH using Curve CVX/ETH pool
    @param _amount Amount of CVX tokens to swap
    @param _min_amount_out Minimum ETH amount expected
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
    @param _min_amount_out Minimum ETH amount expected
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
    @param _min_amount_out Minimum crvUSD amount expected
    @return Amount of crvUSD received from the swap
    """
    if _amount == 0:
        return 0
    return extcall ICurveTriCryptoFactoryNG(constants.CURVE_TRICRV_POOL).exchange(
        1, 0, _amount, _min_amount_out, True, value=_amount
    )


@internal
def _swap_rewards_to_eth() -> uint256:
    """
    @notice Swap CRV and CVX rewards to ETH with oracle-based slippage protection
    @return Total ETH received from swaps
    """
    cvx_balance: uint256 = staticcall IERC20(constants.CVX_TOKEN).balanceOf(self)
    crv_balance: uint256 = staticcall IERC20(constants.CRV_TOKEN).balanceOf(self)

    # Calculate expected ETH values using oracles
    expected_eth_from_cvx: uint256 = self._calc_cvx_value_in_eth(cvx_balance)
    expected_eth_from_crv: uint256 = self._calc_crv_value_in_eth(crv_balance)

    # Apply slippage tolerance to get minimum amounts
    min_eth_from_cvx: uint256 = (
        expected_eth_from_cvx * self.allowed_slippage
    ) // constants.DECIMALS
    min_eth_from_crv: uint256 = (
        expected_eth_from_crv * self.allowed_slippage
    ) // constants.DECIMALS

    eth_from_cvx: uint256 = 0
    eth_from_crv: uint256 = 0

    if cvx_balance > 0:
        eth_from_cvx = self._cvx_to_eth(cvx_balance, min_eth_from_cvx)
        assert eth_from_cvx >= min_eth_from_cvx, "CVX swap slippage"

    if crv_balance > 0:
        eth_from_crv = self._crv_to_eth(crv_balance, min_eth_from_crv)
        assert eth_from_crv >= min_eth_from_crv, "CRV swap slippage"

    return eth_from_cvx + eth_from_crv


@internal
def _swap(
    _caller: address,
    _min_amount_out: uint256,
    _reward_hook_calldata: Bytes[4096],
    _target_hook_calldata: Bytes[4096],
) -> uint256:
    """
    @notice Internal swap function with oracle-based MEV protection
    @param _caller Address to receive caller fee
    @param _min_amount_out Minimum amount expected from final swap
    @param _reward_hook_calldata Calldata for extra reward hook
    @param _target_hook_calldata Calldata for target hook
    @return Amount of target asset received
    """
    # Collect platform fees
    cvx_net: uint256 = 0
    crv_net: uint256 = 0
    eth_net_value: uint256 = 0
    cvx_net, crv_net, eth_net_value = swapper.fee_collector._collect()

    # Swap rewards to ETH with oracle protection
    eth_from_rewards: uint256 = self._swap_rewards_to_eth()

    # Process extra rewards if hook is set
    if swapper.extra_reward_hook != empty(address):
        raw_call(
            swapper.extra_reward_hook,
            _reward_hook_calldata,
            value=0,
        )

    eth_balance: uint256 = self.balance
    expected_crvusd: uint256 = self._calc_eth_value_in_crvusd(eth_balance)
    min_crvusd: uint256 = (expected_crvusd * self.allowed_slippage) // constants.DECIMALS

    # Swap ETH to crvUSD
    crvusd_received: uint256 = self._eth_to_crvusd(eth_balance, min_crvusd)
    assert crvusd_received >= min_crvusd, "ETH to crvUSD slippage"

    # Pay caller fee
    crvusd_after_fee: uint256 = swapper._pay_out_caller_fee(
        _caller, constants.CRVUSD_TOKEN, crvusd_received
    )

    # Process target hook if set
    if swapper.target_hook != empty(address):
        raw_call(
            swapper.target_hook,
            _target_hook_calldata,
            value=0,
        )

    target_asset: address = staticcall IStrategy(swapper.fee_collector.strategy).asset()
    target_asset_balance: uint256 = staticcall IERC20(target_asset).balanceOf(self)
    assert target_asset_balance >= _min_amount_out, "Final slippage"
    assert extcall IERC20(target_asset).transfer(
        swapper.fee_collector.strategy, target_asset_balance, default_return_value=True
    )

    return target_asset_balance

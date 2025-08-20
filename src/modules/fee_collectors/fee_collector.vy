# pragma version 0.4.3
# @license MIT

from ethereum.ercs import IERC20
from src.interfaces import ICurveV2Pool
from src.interfaces import ICurveTriCryptoFactoryNG
from src.interfaces import IStrategy
from src.interfaces import IVaultFactory
from src.modules import constants


# State variables
factory: public(immutable(address))
strategy: public(address)


event TreasuryFeeCollected:
    crv_fee: uint256
    cvx_fee: uint256


event StrategySet:
    strategy: address


@deploy
def __init__(_factory: address):
    """
    @notice Initialize the fee collector contract
    @param _factory Address of the factory that deployed the contract
    @dev The factory address is used to retrieve the treasury address
    """
    factory = _factory


@view
@external
def treasury() -> address:
    return self._treasury()


@view
@internal
def _treasury() -> address:
    return staticcall IVaultFactory(factory).treasury()


@external
def set_strategy(_strategy: address):
    """
    @notice Sets the strategy address
    @param _strategy Address of the strategy contract that can call swap()
    """
    assert self.strategy == empty(address), "Strategy already set"
    assert _strategy != empty(address), "Zero address"
    self.strategy = _strategy
    log StrategySet(strategy=_strategy)


@internal
def _calc_cvx_value_in_eth(_amount: uint256) -> uint256:
    """
    @notice Calculate the ETH value of a given CVX amount using a Curve pool oracle
    @param _amount The amount of CVX tokens to value
    @return The equivalent value in ETH (18 decimals)
    """
    cvx_eth_price: uint256 = staticcall ICurveV2Pool(constants.CURVE_CVX_ETH_POOL).price_oracle()
    return (_amount * cvx_eth_price) // 10**18


@internal
def _calc_crv_value_in_eth(_amount: uint256) -> uint256:
    """
    @notice Calculate the ETH value of a given CRV amount using the Curve TriCrypto pool oracle
    @param _amount The amount of CRV tokens to value
    @return The equivalent value in ETH
    @dev Uses price_oracle(1) for CRV price and price_oracle(0) for ETH price as reference
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
def _calculate_fee_split() -> (uint256, uint256, uint256, uint256, uint256):
    """
    @notice Calculate how much CVX and CRV to take as platform fees
    @return cvx_net Amount of CVX tokens left after fee
    @return crv_net Amount of CRV tokens left after fee
    @return cvx_fee Amount of CVX tokens to take as fee
    @return crv_fee Amount of CRV tokens to take as fee
    @return eth_net_value ETH Value of the rewards after fees
    @dev Prioritizes taking CVX first to cover the platform fee, then CRV if needed
    @dev Fee calculation is based on total ETH value of both token balances
    """
    crv_balance: uint256 = staticcall IERC20(constants.CRV_TOKEN).balanceOf(self)
    cvx_balance: uint256 = staticcall IERC20(constants.CVX_TOKEN).balanceOf(self)
    if crv_balance == 0 and cvx_balance == 0:
        return 0, 0, 0, 0, 0

    crv_eth_value: uint256 = self._calc_crv_value_in_eth(crv_balance)
    cvx_eth_value: uint256 = self._calc_cvx_value_in_eth(cvx_balance)
    total_eth_value: uint256 = crv_eth_value + cvx_eth_value

    # Calculate platform fee in ETH terms
    platform_fee: uint256 = staticcall IStrategy(self.strategy).platform_fee()
    fee_eth_value: uint256 = (total_eth_value * platform_fee) // constants.DECIMALS
    eth_net_value: uint256 = total_eth_value - fee_eth_value

    # Initialize return values
    cvx_fee: uint256 = 0
    crv_fee: uint256 = 0

    # If no fee needed, return everything as remaining
    if fee_eth_value == 0:
        return 0, 0, 0, 0, 0

    if cvx_eth_value >= fee_eth_value:
        # CVX alone can cover the entire fee
        cvx_fee = (fee_eth_value * cvx_balance) // cvx_eth_value
        # All CRV remains for compounding
        crv_fee = 0
    else:
        # CVX covers part of fee, CRV covers the rest
        cvx_fee = cvx_balance  # Take all CVX
        # Calculate remaining fee needed in ETH
        remaining_fee_eth: uint256 = fee_eth_value - cvx_eth_value
        # Convert remaining fee to CRV amount
        crv_fee = (remaining_fee_eth * crv_balance) // crv_eth_value

    return (cvx_balance - cvx_fee), (crv_balance - crv_fee), cvx_fee, crv_fee, eth_net_value


@internal
def _collect() -> (uint256, uint256, uint256):
    """
    @notice Collect platform fees from accumulated CRV and CVX rewards
    @return cvx_net Amount of CVX tokens remaining after fees
    @return crv_net Amount of CRV tokens remaining after fees
    @return eth_net_value ETH Value of the rewards after fees
    @dev Only callable by the strategy contract
    @dev Takes a platform fee (default at 20%) on total reward value
         prioritizing CVX over CRV
    @dev Transfers calculated fees directly to the treasury address
    """
    crv_fee: uint256 = 0
    cvx_fee: uint256 = 0
    crv_net: uint256 = 0
    cvx_net: uint256 = 0
    eth_net_value: uint256 = 0
    treasury: address = self._treasury()
    cvx_net, crv_net, cvx_fee, crv_fee, eth_net_value = self._calculate_fee_split()
    # Transfer fees to fee recipient
    if cvx_fee > 0:
        assert extcall IERC20(constants.CVX_TOKEN).transfer(treasury, cvx_fee)
    if crv_fee > 0:
        assert extcall IERC20(constants.CRV_TOKEN).transfer(treasury, crv_fee)
    log TreasuryFeeCollected(crv_fee=crv_fee, cvx_fee=cvx_fee)
    return cvx_net, crv_net, eth_net_value

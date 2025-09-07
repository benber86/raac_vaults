# pragma version 0.4.3
# pragma nonreentrancy on
# @license MIT

from ethereum.ercs import IERC20
from src.modules import constants
from src.interfaces import IVaultFactory

factory: public(reentrant(immutable(address)))
strategy: public(reentrant(address))
extra_reward_hook: public(reentrant(address))
target_hook: public(reentrant(address))


event RewardHookUpdated:
    new_hook: address


event TargetHookUpdated:
    new_hook: address


event StrategySet:
    strategy: address


event FeeCollected:
    recipient: address
    amount: uint256


@deploy
def __init__(_factory: address):
    """
    @notice Initialize the fee collector contract
    @param _factory Address of the factory that deployed the contract
    @dev The factory address is used to retrieve the treasury address
    """
    factory = _factory


@external
@view
def treasury() -> address:
    return self._treasury()


@internal
@view
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


@external
def set_extra_reward_hook(_new_hook: address):
    """
    @notice Sets a hook contract to handle additional reward tokens beyond CVX/CRV
    @param _new_hook Address of the hook contract to call during swap operations
    @dev Only callable by strategy contract
    @dev Hook contract is responsible for processing extra rewards and returning crvUSD
    @dev Can also be used to unwrap ERC4626 rewards to underlying or withdraw LP tokens
         to underlying in case any of those are given as rewards
    """
    assert msg.sender == self.strategy, "Strategy only"
    self.extra_reward_hook = _new_hook
    log RewardHookUpdated(new_hook=_new_hook)


@external
def set_target_hook(_new_hook: address):
    """
    @notice Sets a hook contract to handle swapping crvUSD to the final asset (LP token)
    @param _new_hook Address of the hook contract to call during swap operations
    @dev Only callable by strategy contract
    @dev Hook contract is responsible for adding crvUSD liq and returning the target LP asset
    """
    assert msg.sender == self.strategy, "Strategy only"
    self.target_hook = _new_hook
    log TargetHookUpdated(new_hook=_new_hook)


@external
def transfer_to_reward_hook(_token: address, _amount: uint256):
    """
    @notice Transfer tokens to the extra reward hook contract
    @param _token Address of the token to transfer
    @param _amount Amount of tokens to transfer
    @dev Only callable by the hook contract itself
    @dev Requires hook contract to be set
    """
    assert self.extra_reward_hook != empty(address), "No hook set"
    assert msg.sender == self.extra_reward_hook, "Hook only"
    assert extcall IERC20(_token).transfer(
        self.extra_reward_hook, _amount, default_return_value=True
    )


@external
def transfer_to_target_hook(_token: address, _amount: uint256):
    """
    @notice Transfer tokens to the target hook contract
    @param _token Address of the token to transfer
    @param _amount Amount of tokens to transfer
    @dev Only callable by the hook contract itself
    @dev Requires hook contract to be set
    """
    assert self.target_hook != empty(address), "No hook set"
    assert msg.sender == self.target_hook, "Hook only"
    assert extcall IERC20(_token).transfer(self.target_hook, _amount, default_return_value=True)


@internal
def _collect_fee(
    _recipient: address, _token: address, _token_amount: uint256, _fee: uint256
) -> uint256:
    """
    @notice Generic fee collection function
    @param _recipient Address to receive the fee
    @param _token Token address for the transfer
    @param _token_amount Total amount to split
    @param _fee Fee percentage (in DECIMALS precision)
    @return Amount remaining after fee deduction
    """
    fee_amount: uint256 = (_token_amount * _fee) // constants.DECIMALS
    remaining_amount: uint256 = _token_amount - fee_amount

    if fee_amount > 0:
        assert extcall IERC20(_token).transfer(_recipient, fee_amount)
        log FeeCollected(recipient=_recipient, amount=fee_amount)

    return remaining_amount


@external
def forward_tokens(
    _tokens: DynArray[address, constants.MAX_REWARD_TOKENS + 2], _recipient: address
):
    """
    @notice Forward specified tokens to recipient address for harvester migration
    @param _tokens Array of token addresses to forward
    @param _recipient Address to receive the tokens
    @dev Only callable by strategy for harvester migration purposes
    """
    assert msg.sender == self.strategy, "Strategy only"
    assert _recipient != empty(address), "Invalid recipient"

    for i: uint256 in range(constants.MAX_REWARD_TOKENS + 2):
        if i == len(_tokens):
            break
        token: address = _tokens[i]
        balance: uint256 = staticcall IERC20(token).balanceOf(self)
        if balance > 0:
            assert extcall IERC20(token).transfer(_recipient, balance)


@external
@payable
def __default__():
    pass

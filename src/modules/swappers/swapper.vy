# pragma version ^0.4.1
# @license MIT

from ethereum.ercs import IERC20
from ..fee_collectors import fee_collector
from .. import constants
from ...interfaces import IStrategy

initializes: fee_collector

exports: fee_collector.__interface__


event RewardHookUpdated:
    new_hook: address


event TargetHookUpdated:
    new_hook: address


extra_reward_hook: public(address)
target_hook: public(address)


@deploy
def __init__(_factory: address):
    fee_collector.__init__(_factory)


@external
def set_extra_reward_hook(_new_hook: address):
    """
    @notice Sets a hook contract to handle additional reward tokens beyond CVX/CRV
    @param _new_hook Address of the hook contract to call during swap operations
    @dev Only callable by strategy contract
    @dev Hook contract is responsible for processing extra rewards and returning ETH
    @dev Can also be used to unwrap ERC4626 rewards to underlying or withdraw LP tokens
         to underlying in case any of those are given as rewards
    """
    assert msg.sender == fee_collector.strategy, "Strategy only"
    self.extra_reward_hook = _new_hook
    log RewardHookUpdated(new_hook=_new_hook)


@external
def set_target_hook(_new_hook: address):
    """
    @notice Sets a hook contract to handle swapping crvUSD to the final asset (LP token)
    @param _new_hook Address of the hook contract to call during swap operations
    @dev Only callable by strategy contract
    @dev Hook contract is responsible for processing extra rewards and returning ETH
    """
    assert msg.sender == fee_collector.strategy, "Strategy only"
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
def _pay_out_caller_fee(_caller: address, _token: address, _token_amount: uint256) -> uint256:
    caller_fee: uint256 = staticcall IStrategy(fee_collector.strategy).caller_fee()
    caller_share: uint256 = (_token_amount * caller_fee) // constants.DECIMALS
    final_share: uint256 = _token_amount - caller_share
    assert extcall IERC20(_token).transfer(_caller, caller_share)
    return final_share


@payable
@external
def __default__():
    pass

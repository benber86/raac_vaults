# pragma version 0.4.3
# pragma nonreentrancy on
# @license MIT

"""
@title RAAC Mock strategy
@custom:contract-name raac_mock_strategy
@author RAAC
@notice A mock contract for testing

"""

from src.modules import constants
from ethereum.ercs import IERC20

asset: public(reentrant(immutable(address)))
vault: public(reentrant(address))


@deploy
def __init__(_asset: address):
    asset = _asset


@external
def set_vault(_vault: address):
    assert self.vault == empty(address), "Vault already set"
    assert _vault != empty(address), "Vault can't be empty"
    self.vault = _vault


@external
def deposit(_amount: uint256):
    assert msg.sender == self.vault, "Vault only"
    pass


@external
def withdraw(_amount: uint256, _receiver: address):
    assert msg.sender == self.vault, "Vault only"
    assert extcall IERC20(asset).transfer(
        _receiver, _amount, default_return_value=True
    ), "erc4626: transfer operation did not succeed"


@external
@view
def total_assets() -> uint256:
    return self._total_assets()


@internal
@view
def _total_assets() -> uint256:
    return staticcall IERC20(asset).balanceOf(self)


@external
def harvest(
    _caller: address,
    _min_amount_out: uint256,
    _extra_rewards: DynArray[address, constants.MAX_REWARD_TOKENS],
    _reward_hook_calldata: Bytes[4096],
    _target_hook_calldata: Bytes[4096],
    _harvester_calldata: Bytes[4096],
):

    # we mimic a harvest by fetching rewards from the caller address for _min_amount_out
    assert extcall IERC20(asset).transferFrom(_caller, self, _min_amount_out)

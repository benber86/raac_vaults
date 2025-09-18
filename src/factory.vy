# pragma version 0.4.3

"""
@title RAAC Stable Vault Factory
@custom:contract-name raac_vault_factory
@license MIT
@author RAAC
@notice Deploys ERC4626 vaults to autocompound yield from Convex positions
@dev Factory creates three interconnected contracts per deployment:
     - Vault: Manages user deposits/withdrawals with ERC4626 compliance
     - Strategy: Handles Convex staking, reward collection, and compounding
     - Harvester: Processes rewards, swaps tokens, and distributes platform fees
     Each vault targets a specific Convex Booster pool and automatically compounds
     CRV/CVX rewards back into the underlying LP position.
"""

from src.modules import constants
from src.modules.utils import conversion
from src.interfaces import IStrategy
from src.interfaces import IVault
from src.interfaces import IBooster
from src.interfaces import IHarvester
from snekmate.auth import ownable
from src import strategy
from ethereum.ercs import IERC20


interface IERC20Detailed:
    def symbol() -> String[20]: view


initializes: ownable
exports: (ownable.transfer_ownership, ownable.renounce_ownership, ownable.owner)


struct VaultRecord:
    vault: address
    booster_id: uint256
    strategy: address
    harvester: address
    token: address


struct Harvester:
    protocol: String[32]
    implementation: address


event HarvesterDeployed:
    index: uint256
    harvester: address


event VaultDeployed:
    id: uint256
    vault: address
    strategy: address
    harvester: address
    token: address


event TreasuryUpdated:
    treasury: address


event HarvesterAdded:
    protocol: String[32]
    implementation: address


VAULT_IMPLEMENTATION: public(immutable(address))
STRATEGY_IMPLEMENTATION: public(immutable(address))

treasury: public(address)

vault_registry: public(HashMap[uint256, VaultRecord])
vaults_deployed: public(uint256)
vault_to_id: public(HashMap[address, uint256])

harvesters: public(DynArray[Harvester, 100])


@external
@view
def harvester_count() -> uint256:
    """
    @notice Get the number of registered harvester implementations
    @return The count of harvesters in the array
    """
    return len(self.harvesters)


@deploy
def __init__(
    _vault_impl: address,
    _strategy_impl: address,
    _harvesters: DynArray[Harvester, 100],
    _treasury: address,
):
    """
    @param _vault_impl Address of the vault implementation contract for blueprint deployment
    @param _strategy_impl Address of the strategy implementation contract for blueprint deployment
    @param _harvesters Array of harvester implementations with their protocol names
    @param _treasury Address where platform fees will be collected
    Implementation Contracts:
    - Vault: Manages user deposits/withdrawals and interfaces with strategies
    - Strategy: Handles Convex Finance integration and reward collection
    - Harvesters: Process rewards, swap tokens, and distribute fees for different protocols
    """
    ownable.__init__()
    ownable._transfer_ownership(msg.sender)

    VAULT_IMPLEMENTATION = _vault_impl
    STRATEGY_IMPLEMENTATION = _strategy_impl

    # Add initial harvesters
    for i: uint256 in range(100):
        if i == len(_harvesters):
            break
        self._add_harvester(_harvesters[i].protocol, _harvesters[i].implementation)

    self.treasury = _treasury


@external
def deploy_new_vault(
    _booster_id: uint256,
    _harvester_index: uint256,
    _harvest_manager: address,
    _strategy_manager: address,
    _harvester_reward_hook: address,
    _harvester_target_hook: address,
    _seed: uint256,
    _profit_max_unlock_time: uint256 = 604800,  # 1 week
) -> (address, address, address):
    """
    @notice Deploys a new permissioned vault and its associated strategy and harvester contracts
            for a given Convex Booster pool.
    @dev
        - Ensures the selected pool is active via Booster.
        - Vault and strategy token metadata are derived from the underlying asset and pool ID.
        - Hooks for extra reward and target can be set optionally.
        - If seed > 0, caller must have approved factory to spend the asset before calling.
    @param _booster_id The Convex Booster id of the pool the vault will autocompound
    @param _harvester_index Index of the harvester implementation in the harvesters array
    @param _harvest_manager Address who will be authorized to execute harvests
    @param _strategy_manager Address who will be authorized to configure the strategy
    @param _harvester_reward_hook Address of extra reward hook for harvester (use address zero to skip).
    @param _harvester_target_hook Address of target hook for harvester (use address zero to skip).
    @param _seed Initial deposit amount to prevent inflation attacks through donation.
               If > 0, transfers asset from msg.sender and deposits into vault.
    @param _profit_max_unlock_time The amount of time profits will be locked for streaming
               (default: 7 days)
    @return vault The deployed vault contract address.
    @return strategy The deployed strategy contract address.
    @return harvester The deployed harvester contract address.
    @custom:reverts
        - If the specified pool is inactive (shut down).
        - If the pool id does not exist in the Booster.
        - If the harvester index is invalid.
        - If seed > 0 and caller hasn't approved factory for asset transfer.
    """

    deployed_harvester: address = self._deploy_harvester(_harvester_index)

    # transaction will revert if id booster is incorrect
    pool_info: (address, address, address, address, address, bool) = staticcall IBooster(
        constants.CONVEX_BOOSTER
    ).poolInfo(_booster_id)


    # ensure pool is not shutdown
    assert pool_info[5] == False

    pool_reward_contract: address = pool_info[3]
    pool_asset: address = pool_info[0]

    # Can be problematic if pool symbol is > 20, however Curve pools LP token's
    # symbol is 10 chars + '-f' suffix.
    pool_asset_symbol: String[20] = staticcall IERC20Detailed(pool_asset).symbol()
    vault_token_name: String[25] = concat("RAAC-", pool_asset_symbol)


    # we use the pool's booster ID as symbol since snekmate limits symbols to 5 chars
    # to avoid URLs in symbols. Some tokens might have similar symbols if Convex ever
    # reaches 100k pools. This is however neither likely in the near future nor a
    # major security risk

    vault_symbol: String[78] = conversion.uint_to_str5(_booster_id)

    deployed_strategy: address = create_from_blueprint(
        STRATEGY_IMPLEMENTATION,
        pool_asset,
        pool_reward_contract,
        deployed_harvester,
        _booster_id,
    )
    deployed_vault: address = create_from_blueprint(
        VAULT_IMPLEMENTATION,
        vault_token_name,
        vault_symbol,
        pool_asset,
        empty(uint256),
        vault_token_name,
        vault_symbol,
        deployed_strategy,
        _profit_max_unlock_time,
    )


    # Grant roles to managers
    extcall IVault(deployed_vault).grantRole(
        staticcall IVault(deployed_vault).STRATEGY_MANAGER_ROLE(),
        _strategy_manager,
    )
    extcall IVault(deployed_vault).grantRole(
        staticcall IVault(deployed_vault).HARVESTER_ROLE(), _harvest_manager
    )

    # Approve spending on pool/staking contracts for strategy
    extcall IStrategy(deployed_strategy).set_approvals()

    # Link strategy and harvester dependencies
    extcall IStrategy(deployed_strategy).set_vault(deployed_vault)
    extcall IHarvester(deployed_harvester).set_strategy(deployed_strategy)

    # Set hooks if specified
    if _harvester_reward_hook != empty(address):
        extcall IVault(deployed_vault).set_extra_reward_hook(_harvester_reward_hook)
    if _harvester_target_hook != empty(address):
        extcall IVault(deployed_vault).set_target_hook(_harvester_target_hook)

    self.vaults_deployed += 1

    self.vault_registry[self.vaults_deployed] = VaultRecord(
        vault=deployed_vault,
        booster_id=_booster_id,
        strategy=deployed_strategy,
        harvester=deployed_harvester,
        token=pool_asset,
    )

    self.vault_to_id[deployed_vault] = self.vaults_deployed

    log VaultDeployed(
        id=self.vaults_deployed,
        vault=deployed_vault,
        strategy=deployed_strategy,
        harvester=deployed_harvester,
        token=pool_asset,
    )

    if _seed > 0:
        assert extcall IERC20(pool_asset).transferFrom(msg.sender, self, _seed)
        assert extcall IERC20(pool_asset).approve(deployed_vault, _seed)
        extcall IVault(deployed_vault).deposit(_seed, msg.sender)

    return deployed_vault, deployed_strategy, deployed_harvester


@external
def set_treasury(_new_treasury: address):
    """
    @notice Set a new treasury address, i.e. address that will receive the platform fees
    @param _new_treasury Treasury address
    """
    ownable._check_owner()
    assert _new_treasury != empty(address), "Treasury cannot be empty"
    self.treasury = _new_treasury
    log TreasuryUpdated(treasury=_new_treasury)


@internal
def _add_harvester(_protocol: String[32], _implementation: address) -> uint256:
    assert _implementation != empty(address), "Implementation cannot be empty"
    self.harvesters.append(Harvester(protocol=_protocol, implementation=_implementation))
    log HarvesterAdded(protocol=_protocol, implementation=_implementation)
    return len(self.harvesters) - 1


@external
def add_harvester(_protocol: String[32], _implementation: address) -> uint256:
    """
    @notice Add a new harvester implementation (owner only)
    @param _protocol Protocol name for the harvester (e.g., "curve", "cow", "balancer")
    @param _implementation Address of the harvester implementation contract
    @return the index of the added harvester in the harvesters array
    """
    ownable._check_owner()
    return self._add_harvester(_protocol, _implementation)


@internal
def _deploy_harvester(_harvester_index: uint256) -> address:
    # Get harvester implementation by index
    assert _harvester_index < len(self.harvesters), "Invalid harvester index"
    harvester_impl: address = self.harvesters[_harvester_index].implementation
    deployed_harvester: address = create_from_blueprint(harvester_impl, self)
    extcall IHarvester(deployed_harvester).set_approvals()
    log HarvesterDeployed(index=_harvester_index, harvester=deployed_harvester)
    return deployed_harvester


@external
def deploy_harvester_instance(_harvester_index: uint256, _vault: address) -> address:
    """
    @notice Deploy a standalone harvester instance tied to an existing vault's strategy
    @dev This function allows deploying additional harvester instances independently
         of vault deployment, useful for replacing or upgrading harvesters for existing
         strategies. The new harvester is deployed with necessary approvals.
    @param _harvester_index Index of the harvester implementation in the harvesters array
    @param _vault Address of the factory-deployed vault contract
    @return The address of the newly deployed harvester instance
    @custom:reverts
        - If the harvester index is invalid (>= harvesters array length)
        - If the vault is not factory-deployed
    """
    vault_id: uint256 = self.vault_to_id[_vault]
    assert self.vault_registry[vault_id].vault == _vault, "Vault not factory deployed"

    deployed_harvester: address = self._deploy_harvester(_harvester_index)
    extcall IHarvester(deployed_harvester).set_strategy(self.vault_registry[vault_id].strategy)
    return deployed_harvester


@external
def update_harvester(_new_harvester: address):
    """
    @notice Update the harvester address in the factory's vault registry
    @dev This function is called by vault contracts through their update_harvester
         function to maintain registry consistency when harvesters are replaced.
    @param _new_harvester Address of the new harvester contract
    @custom:access Only callable by registered vault contracts
    @custom:reverts
        - If the new harvester address is empty (zero address)
        - If the caller is not a registered vault contract
    """
    assert _new_harvester != empty(address), "Invalid harvester"
    vault_id: uint256 = self.vault_to_id[msg.sender]
    assert self.vault_registry[vault_id].vault == msg.sender, "Vault only"
    self.vault_registry[vault_id] = VaultRecord(
        vault=self.vault_registry[vault_id].vault,
        booster_id=self.vault_registry[vault_id].booster_id,
        strategy=self.vault_registry[vault_id].strategy,
        harvester=_new_harvester,
        token=self.vault_registry[vault_id].token,
    )


@external
def update_booster_id(_new_booster_id: uint256):
    """
    @notice Update the booster ID in the factory's vault registry
    @dev This function is called by vault contracts through their update_booster_id
         function to maintain registry consistency when booster pools are shut down.
    @param _new_booster_id New Convex booster pool ID
    @custom:access Only callable by registered vault contracts
    @custom:reverts
        - If the caller is not a registered vault contract
    """
    vault_id: uint256 = self.vault_to_id[msg.sender]
    assert self.vault_registry[vault_id].vault == msg.sender, "Vault only"
    self.vault_registry[vault_id] = VaultRecord(
        vault=self.vault_registry[vault_id].vault,
        booster_id=_new_booster_id,
        strategy=self.vault_registry[vault_id].strategy,
        harvester=self.vault_registry[vault_id].harvester,
        token=self.vault_registry[vault_id].token,
    )

# RAAC Vaults

A yield aggregation system that autocompounds rewards on stablecoin positions (crvUSD pairs only) from Curve and Convex.

## Overview

The factory allows users to create ERC4626-compliant vaults that automatically compound CRV and CVX rewards from Convex staking positions back into the underlying LP tokens.

### Basic Usage Flow
1. Deploy a factory with your chosen harvester type (Curve or CoW)
2. Create a vault for a specific Convex pool using `factory.deploy_new_vault()`
3. Users deposit LP tokens into the vault and receive vault shares
4. Rewards accumulate automatically from Convex staking
5. Anyone with the Harvester role calls `harvest()` to compound rewards
6. Users can withdraw their LP tokens plus compounded rewards anytime

### Out of Audit Scope
The following modules and contracts are not to be audited:

- snekmate's `ownable` and `access_control` modules (already audited)
- `add_liquidity.vy` hook


## Management Roles & Trust Assumptions

### Strategy Manager
- **Intended Actor(s)**: DAO governance
- **Permissions**: Configure strategy parameters, fees, and harvester settings

### Harvester Manager
- **Intended Actor(s)**: Keeper bots
- **Permissions**: Trigger harvest operations
- **Options**:
  - Single trusted keeper for efficiency
  - Whitelist contract for multiple authorized keepers
  - Permissionless contract for fully decentralized harvesting



## Architecture

The protocol consists of four core components that work together to provide automated yield optimization:

### Factory

The **Factory** (`src/factory.vy`) serves as the deployment hub for the entire system.
It uses blueprint contracts to efficiently deploy interconnected vault ecosystems.
The type of vault (Curve or CoW) the factory deploys depends on the harvester implementations specified in the constructor. A factory is only meant to deploy one specific type of vault.

**Key Features:**
- Deploys vault, strategy, and harvester contracts as a unified system
- Manages vault registry and metadata
- Handles role assignments and contract linking
- Supports upgrading harvester implementations

**Key Functions:**
- `deploy_new_vault()` - Creates a complete vault ecosystem for a Convex pool
- `set_treasury()` - Updates platform fee recipient


### Strategy

The **Strategy** (`src/strategy.vy`) acts as the bridge between vaults and Curve/Convex, managing the actual staking operations and reward collection.
Separating out the strategy also opens the possibility of having a permissioned migration feature.

**Key Features:**
- Handles deposits and withdrawals to/from Convex Booster
- Collects CRV, CVX, and extra rewards from staking contracts
- Forwards rewards to harvester for processing
- Manages platform and caller fee configurations

**Key Functions:**
- `deposit()` - Stakes LP tokens in Convex
- `withdraw()` - Unstakes LP tokens from Convex, but doesn't collect rewards as that will happen during harvesting
- `harvest()` - Collects rewards and triggers harvester processing
- `total_assets()` - Returns total staked balance

### Vault

The **Vault** (`src/raac_vault.vy`, `src/modules/vault.vy`) implements ERC4626 standard for tokenized yield strategies with role-based access control.

**Key Features:**
- ERC4626-compliant deposit/withdrawal interface
- Role-based permissions (Administrator, Strategy Manager, Harvester)
- Uses separate strategy and updatable harvester contracts for yield aggregation

**Roles:**
- **Administrator**: Full control over the vault and all roles
- **Strategy Manager**: Controls strategy parameters and harvester settings (intended for DAO)
- **Harvester Role**: Can trigger harvest operations (keeper bots or permissionless contracts)

### Harvester

The protocol supports two harvester implementations, each optimized for different security and MEV protection requirements:

#### Curve Harvester (`src/harvesters/curve_harvester.vy`)
- **Purpose**: Permissioned harvesting with no MEV protection. Harvester can but is not obligated to specify a minimum amount of output tokens.
- **Security**: Minimal slippage protection as users can set `min_amount_out` to zero. Curve pools are somewhat more resistant to sandwiching but this type of vault is nonetheless meant for permissioned harvests where a trusted keeper(s) will compute the appropriate minimum amount of input token off-chain.


#### CoW Harvester (`src/harvesters/cow_harvester.vy`)
- **Purpose**: Uses CoWSwap to sell rewards, ensuring better price execution via competitive auctions
- **Security**: MEV protection through CoW Swap's batch auction mechanism. Generally finds optimum prices as searchers don't typically collude. Although the CoW vaults are meant to be permissioned, they can potentially be made permissionless. For instance, Curve has been using CoW to handle the sales of its fees to crvUSD for several months in a permissionless manner and with no minimum amount specified for the trades. The lack of searcher collusion and the competitive nature of the price discovery process on CoWswap have (so far) offered superior prices.
- **Use Case**: Balance between security and decentralization (Curve uses similar approach for fee burning)

#### Migrating a harvester

Sometimes a harvesting contract's logic may become deprecated (liquidity moved to another pool, swapping contracts were updated, etc.).
In this case it is possible for the strategy manager or the administrator to change the harvester contract.

The expected workflow would be:

1. Deploy new harvester implementation as a blueprint and add it to the factory with `add_harvester()`
2. Deploy an instance of the new blueprint using the factory with `deploy_harvester_instance()`. This links the harvester to the specified strategy and handles approvals.
3. Call `update_harvester()` on the vault contract with the new harvester's address and optionally specify tokens to migrate. This will transfer the strategy's previous hooks to the new harvester and forward any specified tokens from the old harvester to the new one.

### Hooks

**Hooks** provide extensible functionality for processing rewards and adding liquidity:

#### Add Liquidity Hook NG (`src/hooks/add_liquidity_ng.vy`)
- Designed as a post-hook - a final step to get the strategy's target token (usually a Curve LP token)
- Handles one-sided liquidity addition to Curve NG pools
- Converts reward tokens into LP tokens for compounding
- ABI matches NG pools, regular Stableswap pools can be handled with the `add_liquidity.vy` hook.

#### Add Liquidity Hook (`src/hooks/add_liquidity.vy`)
- Same as above but using Curve Stableswap pools

#### Handle Extra Rewards Hook (`src/hooks/handle_extra_rewards.vy`)
- Processes additional reward tokens beyond CRV/CVX
- Can be used to unwrap LP tokens, ERC4626 wrapped tokens and other exotic tokens

The hooks provided are meant as generic examples and may require further adaptation depending on the type of pools and it's rewards.

## Fee Mechanisms

The protocol implements a dual-fee structure to sustain operations and incentivize harvest calls:

### Platform Fee
- **Purpose**: Revenue for protocol treasury and development
- **Default Rate**: 20% (2000 basis points) of harvested crvUSD
- **Maximum**: Set to 30% (3000 basis points)
- **Collection**: Taken as a percentage of the final crvUSD amount after rewards are swapped
- **Distribution**: Sent directly to the treasury address in crvUSD
- **Management**: Configurable by Strategy Manager role

### Caller Fee
- **Purpose**: Compensate harvesters for gas costs and provide harvest incentives
- **Default Rate**: 1% (100 basis points) of harvested crvUSD
- **Maximum**: Set to 10% (1000 basis points)
- **Collection**: Taken as a percentage of the final crvUSD amount after rewards are swapped
- **Recipient**: Address that calls the harvest function (keeper bots, EOAs, etc.)
- **Distribution**: Sent directly to the caller in crvUSD
- **Management**: Configurable by Strategy Manager role - however may need to be handled differently as the caller fee should be able to be adjusted to optimize harvest frequency based on expected yield and gas prices.

## Development

The project uses Moccasin for development and testing:

```bash
# Install dependencies
uv venv
source .venv/bin/activate
uv pip install .
uv run moccasin install
```

The project expect an .env file with the following values:

```
ETHERSCAN_TOKEN=
MAINNET_RPC_URL=
```

## License

MIT License - see individual contract files for details.

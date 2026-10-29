// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {StressRegistry} from "../src/StressRegistry.sol";
import {DemoVault} from "../src/DemoVault.sol";
import {MockLendingMarket} from "../src/MockLendingMarket.sol";

/// @notice Deploys StressRegistry, then DemoVault, then MockLendingMarket (implementationplan.md §12.6).
///
/// Every value comes from environment variables (see .env.example). Each role address is read from
/// <ROLE>_ADDRESS when it is set and non-empty, otherwise derived from <ROLE>_PK, so the deploying
/// machine does not need the other roles' private keys. Only DEPLOYER_PK signs transactions.
///
/// This script never writes deployments/<chainId>.json. Forge runs a script before it sends the
/// transactions, so anything written here could describe a deployment that later fails.
/// scripts/deploy.sh writes the file afterwards, from confirmed receipts and on-chain reads
/// (scripts/write_deployment.py). foundry.toml makes the deployments folder read-only to forge.
/// Private keys are never logged.
contract Deploy is Script {
    uint256 internal constant LOCAL_CHAIN_ID = 31337;
    uint256 internal constant BASE_SEPOLIA_CHAIN_ID = 84532;
    uint256 internal constant MAX_BPS = 10_000;
    uint256 internal constant GIT_SHA_LENGTH = 40;
    /// The mnemonic behind Anvil's and Hardhat's default accounts. Its keys are public, so funds
    /// sent to these accounts on a public network can be taken by anyone.
    string internal constant PUBLIC_DEV_MNEMONIC = "test test test test test test test test test test test junk";
    /// Anvil creates 10 default accounts and Hardhat 20, all from the mnemonic above.
    uint32 internal constant PUBLIC_DEV_ACCOUNTS = 20;

    struct Roles {
        address deployer;
        address attester;
        address malicious;
        address watcher;
        address resolver;
    }

    struct Config {
        uint256 deployerKey;
        Roles roles;
        uint256 bond;
        uint256 challengeWindow;
        uint256 resolutionWindow;
        uint256 toleranceBps;
        string marketIdString;
        uint256 pauseThreshold;
        uint256 ltvThreshold;
        uint256 reducedLtvBps;
        uint256 defaultMaxLtvBps;
        string gitCommit;
    }

    struct Deployment {
        StressRegistry registry;
        DemoVault vault;
        MockLendingMarket market;
        bytes32 marketId;
    }

    error UnsupportedChain(uint256 chainId);
    error ZeroParameter(string name);
    error ZeroRoleAddress(string role);
    error DuplicateRole(string roleA, string roleB);
    error DeployerKeyMismatch();
    error ValueOutOfRange(string name, uint256 value);
    error ToleranceNotZero(uint256 toleranceBps);
    error InvalidThresholds(uint256 ltvThreshold, uint256 pauseThreshold);
    error InvalidLtvBps(uint256 reducedLtvBps, uint256 defaultMaxLtvBps);
    error EmptyMarketId();
    error InvalidGitCommit(string gitCommit);
    error PublicDevAccount(string role, address account);

    // ================================================================ entry

    function run() external returns (Deployment memory) {
        return runWith(loadConfig());
    }

    /// Validates, then deploys. Writes no files.
    function runWith(Config memory cfg) public returns (Deployment memory d) {
        validate(cfg);
        d = deployContracts(cfg);
        _logSummary(cfg, d);
    }

    // =============================================================== config

    function loadConfig() public view returns (Config memory cfg) {
        cfg.deployerKey = vm.envUint("DEPLOYER_PK");
        cfg.roles = Roles({
            deployer: vm.addr(cfg.deployerKey),
            attester: _roleAddress("ATTESTER"),
            malicious: _roleAddress("MALICIOUS"),
            watcher: _roleAddress("WATCHER"),
            resolver: _roleAddress("RESOLVER")
        });
        cfg.bond = vm.envUint("BOND_WEI");
        cfg.challengeWindow = vm.envUint("CHALLENGE_WINDOW_SEC");
        cfg.resolutionWindow = vm.envUint("RESOLUTION_WINDOW_SEC");
        cfg.toleranceBps = vm.envUint("TOLERANCE_BPS");
        cfg.marketIdString = vm.envString("MARKET_ID_STRING");
        cfg.pauseThreshold = vm.envUint("PAUSE_THRESHOLD_USD8");
        cfg.ltvThreshold = vm.envUint("LTV_THRESHOLD_USD8");
        cfg.reducedLtvBps = vm.envUint("REDUCED_LTV_BPS");
        cfg.defaultMaxLtvBps = vm.envUint("DEFAULT_MAX_LTV_BPS");
        cfg.gitCommit = vm.envString("GIT_COMMIT");
    }

    function _roleAddress(string memory role) internal view returns (address) {
        string memory explicitAddress = vm.envOr(string.concat(role, "_ADDRESS"), string(""));
        if (bytes(explicitAddress).length > 0) return vm.parseAddress(explicitAddress);
        return vm.addr(vm.envUint(string.concat(role, "_PK")));
    }

    // =========================================================== validation

    /// Pre-deployment checks from implementationplan.md §12.6 and C-15. Reverts on the first failure.
    function validate(Config memory cfg) public view {
        if (block.chainid != LOCAL_CHAIN_ID && block.chainid != BASE_SEPOLIA_CHAIN_ID) {
            revert UnsupportedChain(block.chainid);
        }
        _validateRoles(cfg);
        if (block.chainid == BASE_SEPOLIA_CHAIN_ID) _rejectPublicDevAccounts(cfg.roles);
        _validateRegistryParams(cfg);
        _validateVaultParams(cfg);
        if (!_isGitSha(cfg.gitCommit)) revert InvalidGitCommit(cfg.gitCommit);
    }

    function _validateRoles(Config memory cfg) internal pure {
        if (cfg.deployerKey == 0) revert ZeroParameter("DEPLOYER_PK");
        if (vm.addr(cfg.deployerKey) != cfg.roles.deployer) revert DeployerKeyMismatch();
        Roles memory r = cfg.roles;
        address[5] memory addrs = [r.deployer, r.attester, r.malicious, r.watcher, r.resolver];
        string[5] memory names = [string("DEPLOYER"), "ATTESTER", "MALICIOUS", "WATCHER", "RESOLVER"];
        for (uint256 i; i < addrs.length; ++i) {
            if (addrs[i] == address(0)) revert ZeroRoleAddress(names[i]);
            for (uint256 j; j < i; ++j) {
                if (addrs[i] == addrs[j]) revert DuplicateRole(names[j], names[i]);
            }
        }
    }

    /// On a public network no role may use a default development account: their keys are public.
    /// Only addresses are compared and reported; keys are never logged.
    function _rejectPublicDevAccounts(Roles memory r) internal pure {
        address[5] memory addrs = [r.deployer, r.attester, r.malicious, r.watcher, r.resolver];
        string[5] memory names = [string("DEPLOYER"), "ATTESTER", "MALICIOUS", "WATCHER", "RESOLVER"];
        for (uint32 i; i < PUBLIC_DEV_ACCOUNTS; ++i) {
            address dev = vm.addr(vm.deriveKey(PUBLIC_DEV_MNEMONIC, i));
            for (uint256 j; j < addrs.length; ++j) {
                if (addrs[j] == dev) revert PublicDevAccount(names[j], dev);
            }
        }
    }

    function _validateRegistryParams(Config memory cfg) internal pure {
        if (cfg.bond == 0) revert ZeroParameter("BOND_WEI");
        _validateWindow("CHALLENGE_WINDOW_SEC", cfg.challengeWindow);
        _validateWindow("RESOLUTION_WINDOW_SEC", cfg.resolutionWindow);
        if (cfg.toleranceBps != 0) revert ToleranceNotZero(cfg.toleranceBps);
        if (bytes(cfg.marketIdString).length == 0) revert EmptyMarketId();
    }

    function _validateWindow(string memory name, uint256 value) internal pure {
        if (value == 0) revert ZeroParameter(name);
        if (value > type(uint64).max) revert ValueOutOfRange(name, value);
    }

    function _validateVaultParams(Config memory cfg) internal pure {
        if (cfg.ltvThreshold == 0 || cfg.ltvThreshold > cfg.pauseThreshold) {
            revert InvalidThresholds(cfg.ltvThreshold, cfg.pauseThreshold);
        }
        if (cfg.reducedLtvBps >= cfg.defaultMaxLtvBps || cfg.defaultMaxLtvBps > MAX_BPS) {
            revert InvalidLtvBps(cfg.reducedLtvBps, cfg.defaultMaxLtvBps);
        }
    }

    /// 40 lowercase hex characters, as printed by `git rev-parse HEAD`.
    function _isGitSha(string memory s) internal pure returns (bool) {
        bytes memory b = bytes(s);
        if (b.length != GIT_SHA_LENGTH) return false;
        for (uint256 i; i < b.length; ++i) {
            bytes1 c = b[i];
            bool isDigit = c >= "0" && c <= "9";
            bool isLowerHex = c >= "a" && c <= "f";
            if (!isDigit && !isLowerHex) return false;
        }
        return true;
    }

    // =============================================================== deploy

    /// keccak256 of the UTF-8 market string; must equal stressproof_core.market_id() (plan C-01).
    function marketIdOf(string memory marketIdString) public pure returns (bytes32) {
        return keccak256(bytes(marketIdString));
    }

    /// Deploys in the documented order. Call through `runWith`, which validates first.
    function deployContracts(Config memory cfg) public returns (Deployment memory d) {
        d.marketId = marketIdOf(cfg.marketIdString);

        vm.startBroadcast(cfg.deployerKey);
        d.registry = new StressRegistry(
            cfg.bond,
            // forge-lint: disable-next-line(unsafe-typecast)
            uint64(cfg.challengeWindow), // range checked in validate
            // forge-lint: disable-next-line(unsafe-typecast)
            uint64(cfg.resolutionWindow), // range checked in validate
            0, // TOLERANCE_BPS, checked to be 0 in validate
            cfg.roles.resolver
        );
        d.vault = new DemoVault(
            d.registry,
            d.marketId,
            cfg.pauseThreshold,
            cfg.ltvThreshold,
            // forge-lint: disable-next-line(unsafe-typecast)
            uint16(cfg.reducedLtvBps), // < defaultMaxLtvBps <= 10000, checked in validate
            // forge-lint: disable-next-line(unsafe-typecast)
            uint16(cfg.defaultMaxLtvBps) // <= 10000, checked in validate
        );
        d.market = new MockLendingMarket(d.vault);
        vm.stopBroadcast();
    }

    // ================================================================= logs

    /// Addresses and parameters only; never keys.
    function _logSummary(Config memory cfg, Deployment memory d) internal view {
        console2.log("chainId", block.chainid);
        console2.log("StressRegistry", address(d.registry));
        console2.log("DemoVault", address(d.vault));
        console2.log("MockLendingMarket", address(d.market));
        console2.log("deployer / vault owner", cfg.roles.deployer);
        console2.log("resolver", cfg.roles.resolver);
        console2.logBytes32(d.marketId);
        console2.log("gitCommit", cfg.gitCommit);
    }
}

const fs = require("node:fs");
const path = require("node:path");

/**
 * Test runs use Hardhat defaults. An explicitly supplied, protected mnemonic
 * file enables a loopback-only development chain; its contents never appear in
 * source, process arguments, or standard output.
 */
function developmentAccounts() {
  const configuredPath = process.env.CEREBRACHAIN_DEVCHAIN_MNEMONIC_FILE;
  if (!configuredPath) return undefined;

  const mnemonicPath = path.resolve(configuredPath);
  const mode = fs.statSync(mnemonicPath).mode & 0o777;
  if ((mode & 0o077) !== 0) {
    throw new Error("Development mnemonic file permissions must be 0600 or stricter.");
  }
  const mnemonic = fs.readFileSync(mnemonicPath, "utf8").trim();
  if (!mnemonic) throw new Error("Development mnemonic file is empty.");

  return {
    mnemonic,
    path: "m/44'/60'/0'/0/",
    initialIndex: 0,
    count: 20,
  };
}

const accounts = developmentAccounts();

module.exports = {
  solidity: "0.8.37",
  networks: {
    hardhat: {
      chainId: 31337,
      ...(accounts ? { accounts } : {}),
    },
  },
};

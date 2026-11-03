"use strict";

const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");
const { spawn } = require("node:child_process");

const packageRoot = path.resolve(__dirname, "..");

function requiredStateDirectory() {
  const index = process.argv.indexOf("--state-dir");
  const value = index >= 0 ? process.argv[index + 1] : undefined;
  if (!value || !path.isAbsolute(value)) {
    throw new Error("An absolute --state-dir is required.");
  }
  return path.resolve(value);
}

function assertSecretFile(secretPath) {
  const metadata = fs.statSync(secretPath);
  if (!metadata.isFile() || (metadata.mode & 0o077) !== 0) {
    throw new Error("Development mnemonic must be a regular file with 0600 permissions.");
  }
}

async function assertPortAvailable() {
  await new Promise((resolve, reject) => {
    const listener = net.createServer();
    listener.once("error", reject);
    listener.listen(18545, "127.0.0.1", () => {
      listener.close((error) => error ? reject(error) : resolve());
    });
  });
}

async function main() {
  const stateDirectory = requiredStateDirectory();
  const mnemonicPath = path.join(stateDirectory, "mnemonic");
  const pidPath = path.join(stateDirectory, "hardhat.pid");
  const hardhatBinary = process.env.HARDHAT_BIN;
  if (!hardhatBinary || !path.isAbsolute(hardhatBinary) || !fs.existsSync(hardhatBinary)) {
    throw new Error("HARDHAT_BIN must reference an existing absolute local binary.");
  }
  if (fs.existsSync(pidPath)) {
    throw new Error("Refusing to overwrite existing development-chain process metadata.");
  }
  assertSecretFile(mnemonicPath);
  await assertPortAvailable();

  const child = spawn(
    hardhatBinary,
    ["node", "--hostname", "127.0.0.1", "--port", "18545"],
    {
      cwd: packageRoot,
      detached: true,
      stdio: "ignore",
      env: {
        ...process.env,
        CEREBRACHAIN_DEVCHAIN_MNEMONIC_FILE: mnemonicPath,
      },
    },
  );
  child.unref();
  fs.writeFileSync(pidPath, `${child.pid}\n`, { encoding: "utf8", mode: 0o600, flag: "wx" });
  fs.chmodSync(pidPath, 0o600);
  process.stdout.write(`Loopback development chain started with PID ${child.pid}.\n`);
}

main().catch((error) => {
  process.stderr.write(`Development-chain startup failed: ${error.message}\n`);
  process.exitCode = 1;
});

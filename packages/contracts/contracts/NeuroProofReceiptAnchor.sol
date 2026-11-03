// SPDX-License-Identifier: MIT
pragma solidity 0.8.37;

/// @title NeuroProofReceiptAnchor
/// @notice Immutable attestation records for off-chain Groth16 verification receipts.
/// @dev This contract does not verify Groth16 proofs, model training, MRI data, or clinical outcomes.
contract NeuroProofReceiptAnchor {
    /// @notice Domain separation for deterministic V2 receipt identifiers.
    bytes32 public constant RECEIPT_DOMAIN = keccak256("cerebrachain-v2:proof-receipt-anchor:v1");

    /// @notice The only status this contract can attest: an authorized account says off-chain verification occurred.
    enum AttestationStatus {
        OffchainGroth16Verified
    }

    enum CommitmentField {
        FederationRound,
        ModelVersion,
        HospitalUpdate,
        ProofArtifact,
        VerificationKey
    }

    /// @notice Privacy-preserving, fixed-size inputs supplied by an authorized anchoring account.
    struct ReceiptInput {
        bytes32 federationRoundCommitment;
        bytes32 modelVersionCommitment;
        bytes32 hospitalUpdateCommitment;
        bytes32 proofArtifactSha256;
        bytes32 verificationKeyId;
    }

    /// @notice Immutable metadata for a successfully anchored off-chain receipt.
    struct Receipt {
        bytes32 federationRoundCommitment;
        bytes32 modelVersionCommitment;
        bytes32 hospitalUpdateCommitment;
        bytes32 proofArtifactSha256;
        bytes32 verificationKeyId;
        AttestationStatus attestationStatus;
        uint64 anchoredAt;
        uint64 anchoredBlock;
        address attestedBy;
    }

    error Unauthorized(address caller);
    error InvalidAddress();
    error InvalidCommitment(CommitmentField field);
    error ReceiptAlreadyAnchored(bytes32 receiptId);
    error ReceiptNotFound(bytes32 receiptId);

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event AnchoringAccountUpdated(address indexed account, bool authorized, address indexed updatedBy);
    event ReceiptAnchored(
        bytes32 indexed receiptId,
        bytes32 indexed federationRoundCommitment,
        bytes32 indexed hospitalUpdateCommitment,
        bytes32 modelVersionCommitment,
        bytes32 proofArtifactSha256,
        bytes32 verificationKeyId,
        AttestationStatus attestationStatus,
        address attestedBy,
        uint64 anchoredAt,
        uint64 anchoredBlock
    );

    address public owner;
    mapping(address account => bool authorized) private _anchoringAccounts;
    mapping(bytes32 receiptId => bool exists) private _receiptExists;
    mapping(bytes32 receiptId => Receipt receipt) private _receipts;

    modifier onlyOwner() {
        if (msg.sender != owner) revert Unauthorized(msg.sender);
        _;
    }

    modifier onlyAnchoringAccount() {
        if (!_anchoringAccounts[msg.sender]) revert Unauthorized(msg.sender);
        _;
    }

    /// @param initialAnchoringAccount Explicit account authorized to attest receipts at deployment.
    constructor(address initialAnchoringAccount) {
        if (initialAnchoringAccount == address(0)) revert InvalidAddress();

        owner = msg.sender;
        _anchoringAccounts[initialAnchoringAccount] = true;

        emit OwnershipTransferred(address(0), msg.sender);
        emit AnchoringAccountUpdated(initialAnchoringAccount, true, msg.sender);
    }

    /// @notice Returns whether an account may attest off-chain verification receipts.
    function isAnchoringAccount(address account) external view returns (bool) {
        return _anchoringAccounts[account];
    }

    /// @notice Explicitly authorizes or revokes a receipt-attestation account.
    function setAnchoringAccount(address account, bool authorized) external onlyOwner {
        if (account == address(0)) revert InvalidAddress();
        _anchoringAccounts[account] = authorized;
        emit AnchoringAccountUpdated(account, authorized, msg.sender);
    }

    /// @notice Transfers the sole administrative authority. There is no hidden admin path.
    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert InvalidAddress();
        address previousOwner = owner;
        owner = newOwner;
        emit OwnershipTransferred(previousOwner, newOwner);
    }

    /// @notice Computes the canonical receipt identity from all receipt commitments.
    function computeReceiptId(ReceiptInput calldata input) public pure returns (bytes32) {
        return keccak256(
            abi.encode(
                RECEIPT_DOMAIN,
                input.federationRoundCommitment,
                input.modelVersionCommitment,
                input.hospitalUpdateCommitment,
                input.proofArtifactSha256,
                input.verificationKeyId
            )
        );
    }

    /// @notice Records one immutable attestation that an authorized off-chain verifier accepted a receipt.
    /// @dev This function does not independently execute Groth16 verification.
    function anchorReceipt(ReceiptInput calldata input)
        external
        onlyAnchoringAccount
        returns (bytes32 receiptId)
    {
        _validateInput(input);
        receiptId = computeReceiptId(input);
        if (_receiptExists[receiptId]) revert ReceiptAlreadyAnchored(receiptId);

        Receipt memory receipt = Receipt({
            federationRoundCommitment: input.federationRoundCommitment,
            modelVersionCommitment: input.modelVersionCommitment,
            hospitalUpdateCommitment: input.hospitalUpdateCommitment,
            proofArtifactSha256: input.proofArtifactSha256,
            verificationKeyId: input.verificationKeyId,
            attestationStatus: AttestationStatus.OffchainGroth16Verified,
            anchoredAt: uint64(block.timestamp),
            anchoredBlock: uint64(block.number),
            attestedBy: msg.sender
        });

        _receiptExists[receiptId] = true;
        _receipts[receiptId] = receipt;

        emit ReceiptAnchored(
            receiptId,
            receipt.federationRoundCommitment,
            receipt.hospitalUpdateCommitment,
            receipt.modelVersionCommitment,
            receipt.proofArtifactSha256,
            receipt.verificationKeyId,
            receipt.attestationStatus,
            receipt.attestedBy,
            receipt.anchoredAt,
            receipt.anchoredBlock
        );
    }

    /// @notice Returns immutable receipt metadata, or reverts when the receipt was never anchored.
    function getReceipt(bytes32 receiptId) external view returns (Receipt memory) {
        if (!_receiptExists[receiptId]) revert ReceiptNotFound(receiptId);
        return _receipts[receiptId];
    }

    /// @notice Returns whether the deterministic receipt identifier has been anchored.
    function receiptExists(bytes32 receiptId) external view returns (bool) {
        return _receiptExists[receiptId];
    }

    function _validateInput(ReceiptInput calldata input) private pure {
        if (input.federationRoundCommitment == bytes32(0)) {
            revert InvalidCommitment(CommitmentField.FederationRound);
        }
        if (input.modelVersionCommitment == bytes32(0)) {
            revert InvalidCommitment(CommitmentField.ModelVersion);
        }
        if (input.hospitalUpdateCommitment == bytes32(0)) {
            revert InvalidCommitment(CommitmentField.HospitalUpdate);
        }
        if (input.proofArtifactSha256 == bytes32(0)) {
            revert InvalidCommitment(CommitmentField.ProofArtifact);
        }
        if (input.verificationKeyId == bytes32(0)) {
            revert InvalidCommitment(CommitmentField.VerificationKey);
        }
    }
}

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title PrescriptionRegistry (reference contract, research demonstrator)
/// @notice States in Solidity the same rules as vmdt/contracts.py. Only 32-byte
///         fingerprints (salted hashes) are stored; no personal or clinical data.
///         Not audited and not deployed. Do not use with real patients.
contract PrescriptionRegistry {
    enum Status { None, Requested, Reviewed, Signed, Rejected, Overridden }
    enum Outcome { Green, Amber, Red, HardStop }
    enum Decision { Approve, ApproveWithChanges, AcceptAlternative, Override, Reject }

    struct Consent { bool active; uint64 expires; }
    struct Case {
        Status status;
        Outcome outcome;
        bool alternativeOffered;
        bytes32 patient;
        bytes32 prescription;
    }

    address public immutable authority;                 // e.g. the integrated care board
    mapping(address => bool) public prescribers;        // accounts allowed to decide
    mapping(bytes32 => Consent) public consents;        // patient fingerprint => consent
    mapping(bytes32 => Case) public cases;              // case fingerprint => case

    event ConsentGranted(bytes32 indexed patient, uint64 expires);
    event ConsentRevoked(bytes32 indexed patient);
    event Accessed(bytes32 indexed patient, bytes32 indexed accessor, bytes32 fieldsHash);
    event Requested(bytes32 indexed caseId, bytes32 indexed patient);
    event Reviewed(bytes32 indexed caseId, Outcome outcome, uint8 experts, uint8 objections, bool alternativeOffered);
    event Decided(bytes32 indexed caseId, Status status, Decision decision, address indexed prescriber, bytes32 prescription, bytes32 reason);

    modifier onlyAuthority() { require(msg.sender == authority, "not authority"); _; }
    modifier onlyPrescriber() { require(prescribers[msg.sender], "not a prescriber"); _; }

    constructor() { authority = msg.sender; }

    function setPrescriber(address who, bool allowed) external onlyAuthority { prescribers[who] = allowed; }

    function consentActive(bytes32 patient) public view returns (bool) {
        Consent memory c = consents[patient];
        return c.active && (c.expires == 0 || block.timestamp < c.expires);
    }

    function grantConsent(bytes32 patient, uint64 expires) external onlyPrescriber {
        consents[patient] = Consent(true, expires);
        emit ConsentGranted(patient, expires);
    }

    function revokeConsent(bytes32 patient) external onlyPrescriber {
        require(consents[patient].active, "no consent");
        consents[patient].active = false;
        emit ConsentRevoked(patient);
    }

    function logAccess(bytes32 patient, bytes32 accessor, bytes32 fieldsHash) external onlyPrescriber {
        require(consentActive(patient), "no active consent");
        emit Accessed(patient, accessor, fieldsHash);
    }

    function request(bytes32 caseId, bytes32 patient) external onlyPrescriber {
        require(consentActive(patient), "no active consent");
        require(cases[caseId].status == Status.None, "case exists");
        cases[caseId] = Case(Status.Requested, Outcome.Green, false, patient, bytes32(0));
        emit Requested(caseId, patient);
    }

    function review(bytes32 caseId, Outcome outcome, uint8 experts, uint8 objections, bool alternativeOffered) external onlyPrescriber {
        Case storage c = cases[caseId];
        require(c.status == Status.Requested, "not requested");
        c.status = Status.Reviewed;
        c.outcome = outcome;
        c.alternativeOffered = alternativeOffered;
        emit Reviewed(caseId, outcome, experts, objections, alternativeOffered);
    }

    function decide(bytes32 caseId, Decision decision, bytes32 prescription, bytes32 reason, bool acknowledged) external onlyPrescriber {
        Case storage c = cases[caseId];
        require(c.status == Status.Reviewed, "decided once only");
        require(consentActive(c.patient), "consent withdrawn");
        bool escalated = c.outcome == Outcome.Red || c.outcome == Outcome.HardStop;
        if (decision == Decision.Approve || decision == Decision.ApproveWithChanges) {
            require(!escalated, "escalated case cannot be approved");
        }
        if (decision == Decision.Approve && c.outcome == Outcome.Amber) {
            require(acknowledged, "cautions not acknowledged");
        }
        if (decision == Decision.AcceptAlternative) {
            require(c.alternativeOffered, "no safer option offered");
        }
        if (decision == Decision.Override) {
            require(escalated && reason != bytes32(0), "override needs escalation and reason");
        }
        if (decision != Decision.Reject) {
            require(prescription != bytes32(0), "no prescription fingerprint");
        }
        c.status = decision == Decision.Reject ? Status.Rejected : (decision == Decision.Override ? Status.Overridden : Status.Signed);
        c.prescription = prescription;
        emit Decided(caseId, c.status, decision, msg.sender, prescription, reason);
    }

    /// @notice What a pharmacy checks before dispensing.
    function isValidPrescription(bytes32 caseId, bytes32 prescription) external view returns (bool) {
        Case memory c = cases[caseId];
        return (c.status == Status.Signed || c.status == Status.Overridden) && c.prescription == prescription;
    }
}

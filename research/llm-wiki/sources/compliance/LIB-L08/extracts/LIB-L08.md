# Architectural Requirements for Supporting AI Agents on the Internet (draft-daniel-ai-agent-internet-architecture-03)

- Source ID: LIB-L08
- Source: https://datatracker.ietf.org/doc/draft-daniel-ai-agent-internet-architecture/
- File: draft-daniel-ai-agent-internet-architecture-03.txt (사용자가 제공한 "AI 컴플라이언스 관련 문서 모음.zip" 안의 사본, 2026-10-17 입수)
- SHA256: 741bac5bc0d8bad1e9f772d090094a76d4c5ef64ab3baf2956270c86e19e23a6
- Bytes: 65667
- Pages: None
- Distribution: public-under-license
- Method: plain-text copy of the Internet-Draft; no transformation

---





Network Working Group                                         S. D. Park
Internet-Draft                                       Samsung Electronics
Intended status: Informational                               I. Siddique
Expires: 1 March 2027                                             Opaque
                                                          28 August 2026


  Architectural Requirements for Supporting AI Agents on the Internet
             draft-daniel-ai-agent-internet-architecture-03

Abstract

   Autonomous AI agents are evolving from interactive assistants into
   networked software workloads that discover services, invoke tools,
   delegate authority, transact, communicate with other agents, and act
   asynchronously on behalf of humans and organizations.  Existing
   Internet protocols provide strong foundations, but agent autonomy,
   dynamic delegation, machine-speed execution, long and unpredictable
   model-processing intervals, and cross-domain interaction create
   requirements that span multiple protocol families.

   This document describes architectural requirements for supporting AI
   agents on the Internet across naming and discovery, HTTP,
   authentication, authorization and delegation, TLS and workload
   identity, transport and connection continuity, asynchronous
   messaging, capability and intent-based resolution, payments,
   provenance, auditability, revocation, security, and privacy.  It
   favors profiling and extending existing Internet protocols over
   defining a monolithic new agent protocol, and identifies the need for
   IETF-wide architectural coordination.

Status of This Memo

   This Internet-Draft is submitted in full conformance with the
   provisions of BCP 78 and BCP 79.

   Internet-Drafts are working documents of the Internet Engineering
   Task Force (IETF).  Note that other groups may also distribute
   working documents as Internet-Drafts.  The list of current Internet-
   Drafts is at https://datatracker.ietf.org/drafts/current/.

   Internet-Drafts are draft documents valid for a maximum of six months
   and may be updated, replaced, or obsoleted by other documents at any
   time.  It is inappropriate to use Internet-Drafts as reference
   material or to cite them other than as "work in progress."

   This Internet-Draft will expire on 1 March 2027.




Park & Siddique           Expires 1 March 2027                  [Page 1]

Internet-Draft       AI Agent Internet Architecture          August 2026


Copyright Notice

   Copyright (c) 2026 IETF Trust and the persons identified as the
   document authors.  All rights reserved.

   This document is subject to BCP 78 and the IETF Trust's Legal
   Provisions Relating to IETF Documents (https://trustee.ietf.org/
   license-info) in effect on the date of publication of this document.
   Please review these documents carefully, as they describe your rights
   and restrictions with respect to this document.  Code Components
   extracted from this document must include Revised BSD License text as
   described in Section 4.e of the Trust Legal Provisions and are
   provided without warranty as described in the Revised BSD License.

Table of Contents

   1.  Introduction  . . . . . . . . . . . . . . . . . . . . . . . .   3
   2.  Terminology and Conventions . . . . . . . . . . . . . . . . .   3
   3.  Scope and Non-Goals . . . . . . . . . . . . . . . . . . . . .   4
   4.  Problem Statement . . . . . . . . . . . . . . . . . . . . . .   5
   5.  Architectural Principles  . . . . . . . . . . . . . . . . . .   6
   6.  Roles and Identity Relationships  . . . . . . . . . . . . . .   7
   7.  Reference Interaction Model . . . . . . . . . . . . . . . . .   8
   8.  Naming and Discovery Requirements . . . . . . . . . . . . . .   9
   9.  HTTP Requirements . . . . . . . . . . . . . . . . . . . . . .   9
   10. Transport and Connection Continuity for Long-Running Agent
           Operations  . . . . . . . . . . . . . . . . . . . . . . .  11
   11. Task Lifecycle Requirements . . . . . . . . . . . . . . . . .  13
   12. Authentication, Authorization, and Delegation . . . . . . . .  13
   13. TLS, PKI, Workload Identity, and Trust  . . . . . . . . . . .  14
   14. Asynchronous Agent Communication  . . . . . . . . . . . . . .  15
   15. Capability and Intent-Based Resolution  . . . . . . . . . . .  16
   16. Payment and Economic Interaction  . . . . . . . . . . . . . .  16
   17. Provenance, Auditability, and Accountability  . . . . . . . .  17
   18. Revocation, Suspension, and Emergency Control . . . . . . . .  18
   19. Security Considerations . . . . . . . . . . . . . . . . . . .  18
     19.1.  Identity and Execution Integrity . . . . . . . . . . . .  19
     19.2.  Confused Deputies and Delegation Amplification . . . . .  19
     19.3.  Replay, Retry, and Duplicate Execution . . . . . . . . .  19
     19.4.  Discovery and Negotiation Attacks  . . . . . . . . . . .  19
     19.5.  Asynchronous Relays and Callbacks  . . . . . . . . . . .  20
     19.6.  Resource and Economic Exhaustion . . . . . . . . . . . .  20
     19.7.  Revocation Races . . . . . . . . . . . . . . . . . . . .  20
     19.8.  Evidence Limitations . . . . . . . . . . . . . . . . . .  20
   20. Relationship to Existing Agent Protocols  . . . . . . . . . .  20
   21. Requirements and Gap Analysis . . . . . . . . . . . . . . . .  21
   22. Candidate IETF Work Items . . . . . . . . . . . . . . . . . .  23
   23. Current IETF Work Landscape and Coordination Gap  . . . . . .  23



Park & Siddique           Expires 1 March 2027                  [Page 2]

Internet-Draft       AI Agent Internet Architecture          August 2026


   24. Recommendation for IETF-Wide Coordination of AI Agent Protocol
           Work  . . . . . . . . . . . . . . . . . . . . . . . . . .  24
   25. Privacy Considerations  . . . . . . . . . . . . . . . . . . .  24
   26. Operational Considerations  . . . . . . . . . . . . . . . . .  25
   27. IANA Considerations . . . . . . . . . . . . . . . . . . . . .  26
   28. Open Issues . . . . . . . . . . . . . . . . . . . . . . . . .  26
   29. Normative References  . . . . . . . . . . . . . . . . . . . .  26
   30. Informative References  . . . . . . . . . . . . . . . . . . .  27
   Authors' Addresses  . . . . . . . . . . . . . . . . . . . . . . .  28

1.  Introduction

   AI agents are becoming autonomous Internet participants rather than
   merely user-interface features.  An agent can interpret a goal,
   discover remote services, acquire or present delegated authority,
   select another agent, invoke tools, initiate payments, maintain
   state, and continue work without a human being present for each
   network transaction.

   Application protocols and frameworks can address important agent
   interaction patterns, but they do not by themselves solve Internet-
   wide problems of naming, discovery, identity, delegated
   authorization, trust, payment negotiation, asynchronous delivery,
   provenance, and accountability across administrative domains.

   AI-agent-related Internet-Drafts are already emerging across
   authentication and authorization, discovery, agent-to-agent and
   agent-to-tool communication, transport, and related areas.  This
   breadth indicates that supporting AI agents is not a single
   application-protocol problem.  It also creates a coordination risk if
   common concepts such as agent identity, capability, delegation,
   discovery metadata, intent, and transaction context are defined
   independently.

   This document defines architectural requirements for supporting AI
   agents on the Internet.  It does not define a separate Internet, a
   new network layer, or a universal agent protocol.  The preferred
   direction is coordinated evolution of existing Internet mechanisms
   and new mechanisms only where demonstrated gaps remain.

2.  Terminology and Conventions

   The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD,
   SHOULD NOT, RECOMMENDED, NOT RECOMMENDED, MAY, and OPTIONAL in this
   document are to be interpreted as described in BCP 14 [RFC2119]
   [RFC8174] when, and only when, they appear in all capitals.

   Agent:  An autonomous or semi-autonomous software entity that can



Park & Siddique           Expires 1 March 2027                  [Page 3]

Internet-Draft       AI Agent Internet Architecture          August 2026


      take network actions based on goals, policies, delegated
      authority, and contextual state.

   Principal:  A human, organization, workload, service, or agent whose
      identity or authority is relevant to an action.

   Delegation:  A grant of authority from one principal to another,
      including scope, time, value, context, or re-delegation
      constraints.

   Capability:  A machine-readable description of an operation or
      service that an agent can provide.

   Intent:  The desired outcome or declared purpose associated with an
      agent action.  Intent is not, by itself, an authorization signal.

   Agent Descriptor:  Machine-readable metadata describing an agent's
      identity, capabilities, endpoints, protocols, security
      requirements, and related operational properties.

   AI Agent Internet Architecture:  The set of Internet protocol
      mechanisms and coordinated extensions needed to support autonomous
      AI agents across administrative and trust boundaries.  This term
      does not imply replacement of the existing Internet architecture.

   Inference-Induced Transport Idleness:  A period in which an agent
      task remains active while little or no application data traverses
      an associated transport connection because a model or service is
      performing inference, reasoning, retrieval, tool execution, or
      related processing.

3.  Scope and Non-Goals

   This document focuses on protocol-layer interoperability across
   independently administered Internet domains.  It covers discovery,
   identity, authorization and delegation, trust establishment, HTTP
   interaction, transport behavior for long-running agent operations,
   payment negotiation, asynchronous communication, capability
   resolution, provenance, auditability, revocation, and privacy.

   This document does not standardize model behavior, prompt formats,
   reasoning traces, agent planning algorithms, model evaluation, or a
   universal agent runtime.  It does not select a single application
   framework as the interaction protocol for all agents.  However,
   characteristics of model execution that materially affect Internet
   protocol behavior, such as long and unpredictable processing
   intervals, are within scope when they create transport, connection-
   management, or application-protocol requirements.



Park & Siddique           Expires 1 March 2027                  [Page 4]

Internet-Draft       AI Agent Internet Architecture          August 2026


4.  Problem Statement

   Existing Internet protocols can transport agent traffic, but they do
   not consistently expose the semantics required when autonomous
   software acts as a principal.  A server can authenticate a TLS peer
   or validate an OAuth access token without necessarily knowing which
   agent is acting, which human or organization delegated the action,
   whether re-delegation was permitted, or whether the transaction
   remains within a spending or operational limit.

   DNS can locate hosts and services, but Internet-wide agent discovery
   can require resolution by organization, agent name, capability,
   supported protocol, security profile, or intent.  Long-running agent
   tasks can also require asynchronous delivery and correlation beyond a
   single synchronous request/response exchange.

   AI-agent interactions can exhibit timing characteristics that differ
   substantially from conventional Web transactions.  After an agent
   sends a request to a remote model or agent service, the remote system
   can spend seconds, minutes, or potentially longer performing model
   inference, reasoning, retrieval, tool execution, or multi-agent
   coordination before producing application data in response.

   During this processing interval, the underlying transport connection
   can remain logically valid while carrying little or no application
   data.  Application servers, HTTP intermediaries, reverse proxies,
   load balancers, NATs, firewalls, or other stateful middleboxes can
   interpret such periods of silence as inactivity and apply idle or
   request timeouts that terminate or discard state associated with an
   otherwise valid agent operation.

   Even when a TCP connection remains established, a long application-
   limited or idle interval has implications for congestion-control
   state.  Previously measured path capacity cannot necessarily be
   assumed to remain valid after a long idle period.  TCP congestion-
   control mechanisms therefore can reduce or revalidate the congestion
   window before transmission resumes [RFC5681] [RFC7661].  A large
   model response generated after a lengthy inference interval can
   consequently experience a renewed congestion-window growth phase even
   though the application regards the operation as one continuous
   transaction.

   The architecture therefore distinguishes task lifetime, application
   transaction lifetime, transport connection lifetime, and network
   state lifetime.  These lifetimes cannot be assumed to be identical.






Park & Siddique           Expires 1 March 2027                  [Page 5]

Internet-Draft       AI Agent Internet Architecture          August 2026


   An interoperable architecture therefore needs machine-processable
   answers to: who is acting; who operates the agent; on whose behalf it
   acts; what it is authorized to do; whether that authority may be
   delegated; what the counterparty can do; how the counterparty is
   discovered and authenticated; what protocol and security profile to
   use; what payment is required; what evidence remains after the
   action; and whether a long-running task remains active independently
   of a particular transport connection.

5.  Architectural Principles

   *Evolution Before Replacement:* Agent-related mechanisms SHOULD reuse
   deployed Internet protocols and registries where practical.  A new
   protocol SHOULD be introduced only when existing mechanisms cannot
   provide the required semantics, security properties, deployment
   model, or scale.

   *Separation of Concerns:* Identity, authentication, authorization,
   delegation, capability, intent, trust, payment, and audit are
   distinct concepts and MUST NOT be implicitly conflated.

   *Independent Trust Signals:* Authentication establishes control of a
   credential associated with an agent or workload.  Authorization
   determines whether that authenticated principal is permitted to
   perform an action.  Remote attestation can provide additional
   evidence concerning the software composition, configuration, or
   execution state associated with that principal.  Audit mechanisms can
   record which identity, authorization, and attestation information
   informed a decision.  These functions are complementary and MUST NOT
   be treated as interchangeable trust signals.

   *Cross-Domain Operation:* Mechanisms MUST assume that agents,
   principals, authorization services, resource servers, and discovery
   infrastructure can belong to different administrative domains.

   *Least Authority:* Delegated authority SHOULD be narrowly scoped by
   operation, audience, resource, time, value, and context.  Re-
   delegation SHOULD be explicit rather than assumed.

   *Human and Organizational Accountability:* When an agent acts for a
   human or organization, protocols SHOULD preserve sufficient
   verifiable evidence to identify the accountable principal without
   exposing unnecessary personal data.

   *Decentralized Deployability:* The architecture SHOULD NOT require a
   single global agent registry, identity provider, payment provider, or
   trust-score operator.




Park & Siddique           Expires 1 March 2027                  [Page 6]

Internet-Draft       AI Agent Internet Architecture          August 2026


   *Processing-Time Independence:* Internet mechanisms supporting AI
   agents SHOULD NOT assume that useful application data will be
   generated within a short or predictable interval after a request is
   accepted.  Protocol designs SHOULD distinguish remote computation or
   inference delay from network failure and SHOULD allow application
   task state to survive transport interruption or transport-state
   expiration where practical.

6.  Roles and Identity Relationships

   An agent interaction can involve multiple identities and
   administrative roles.  These roles can be co-located, but they are
   not semantically interchangeable.

   Agent Instance:  A particular running instance of agent software.
      Multiple instances can implement the same Agent Service.

   Agent Service:  A network-accessible service that accepts or performs
      agent tasks.

   Agent Operator:  The organization or person responsible for deploying
      or operating an Agent Service or Agent Instance.

   Delegating Principal:  The human, organization, service, or agent
      that grants authority for an agent action.

   Credential Holder:  The workload or component that possesses or
      controls a credential used to authenticate a request.  Credential
      possession does not, by itself, establish software integrity,
      delegated authority, or alignment with the Delegating Principal's
      intent.

   Resource Server:  The service that hosts or controls the resource on
      which an agent requests an action.

   Verifier:  A role that appraises Evidence according to an appraisal
      policy and produces an Attestation Result, as described by the
      RATS architecture.

   Relying Party:  A role that uses identity, authorization,
      attestation, or other information to make a policy decision.

   An agent protocol MUST NOT assume that endpoint identity, Agent
   Service identity, Agent Instance identity, Agent Operator identity,
   Credential Holder identity, or Delegating Principal identity are the
   same.  A protocol MAY bind two or more of these roles where that
   binding is explicit, verifiable, and appropriate to the deployment.




Park & Siddique           Expires 1 March 2027                  [Page 7]

Internet-Draft       AI Agent Internet Architecture          August 2026


7.  Reference Interaction Model

   The reference model distinguishes task lifetime from any individual
   message, HTTP exchange, or transport connection.  A task can move
   through proposed, accepted, and executing states before reaching a
   succeeded, failed, cancelled, or expired terminal state.  A protocol
   can define additional states, but it MUST define which transitions
   are terminal and which party is authorized to request each non-
   automatic transition.

   1.  A Delegating Principal grants an agent authority constrained by
       audience, operation, resource, time, value, and re-delegation
       policy.

   2.  The agent discovers candidate Agent Services and the applicable
       protocol, authentication, authorization, and security profiles.

   3.  The agent authenticates and presents authorization evidence for a
       specific requested action.

   4.  The Resource Server evaluates effective authority and either
       rejects the request or accepts it as a task.

   5.  On acceptance, the Resource Server returns a task identifier and
       procedures for status retrieval, cancellation, and result
       retrieval.  The task identifier is not assumed to be an
       authorization credential.

   6.  Task execution can outlive the original HTTP exchange or
       transport connection.  A later connection can retrieve status or
       results without causing the task to execute again.

   7.  When payment is required, payment authorization and the receipt
       are bound to the resource request, task, and applicable spending
       authority.

   8.  Material identity, authorization, policy, payment, result, and
       optional attestation information is retained or referenced as
       privacy-preserving audit evidence.

   9.  Revocation processing distinguishes authority to begin a new task
       from authority governing a task that has already been accepted or
       completed.

   Protocol profiles MUST specify which phases they implement and how
   security context is preserved across phase or transport changes.





Park & Siddique           Expires 1 March 2027                  [Page 8]

Internet-Draft       AI Agent Internet Architecture          August 2026


8.  Naming and Discovery Requirements

   DNS is a natural component of agent discovery because it provides
   globally delegated naming, caching, service discovery, and security
   extensions.  Relevant deployed foundations include DNSSEC [RFC4033]
   and SVCB/HTTPS service binding [RFC9460].  DNS for AI Discovery (DNS-
   AID) is one example of current IETF work in this space.

   REQ-DISC-1: An agent discovery mechanism MUST support discovery when
   an organization and agent identifier are known.

   REQ-DISC-2: It SHOULD support discovery when the organization is
   known but the specific agent is not, using capability or service
   metadata.

   REQ-DISC-3: The architecture SHOULD define how capability-only or
   intent-assisted discovery can be federated without requiring a
   mandatory centralized registry.

   REQ-DISC-4: Discovery results SHOULD be able to express endpoint,
   protocol, protocol version, capability identifiers, authentication
   requirements, authorization metadata, payment support, and relevant
   trust material.

   REQ-DISC-5: Discovery metadata MUST have a mechanism for authenticity
   and integrity protection.

   REQ-DISC-6: Discovery mechanisms SHOULD define caching, freshness,
   negative caching, key rotation, endpoint mobility, and downgrade
   behavior.

   REQ-DISC-7: Discovery metadata MUST distinguish self-asserted
   capability or reputation claims from claims supported by
   independently verifiable evidence.

   REQ-DISC-8: Discovery mechanisms MUST define behavior for stale,
   revoked, or downgraded security metadata.

   REQ-DISC-9: Discovery of an endpoint MUST NOT, by itself, imply that
   the endpoint is authorized, trustworthy, or suitable for a requested
   action.

9.  HTTP Requirements

   HTTP is expected to remain a primary substrate for agent
   interactions.  Agent requirements should preferentially use existing
   HTTP extensibility mechanisms, including HTTP semantics [RFC9110],
   HTTP Message Signatures [RFC9421], and Well-Known URIs [RFC8615].



Park & Siddique           Expires 1 March 2027                  [Page 9]

Internet-Draft       AI Agent Internet Architecture          August 2026


   *Programmatic Payment:* HTTP 402 Payment Required and x402-style
   flows demonstrate a machine-operable payment challenge model.
   Generic standardization should remain independent of a particular
   currency, ledger, wallet, or settlement provider.

   REQ-HTTP-1: A payment challenge SHOULD identify the payment scheme,
   amount or pricing rule, asset or unit, recipient, expiration, replay
   constraints, and verification method in machine-readable form.

   REQ-HTTP-2: Payment authorization SHOULD be bindable to the agent's
   delegated spending authority, request target, and transaction
   context.

   REQ-HTTP-3: Payment mechanisms SHOULD support receipts and SHOULD
   define failure, retry, duplicate-payment, cancellation, and refund
   semantics.

   *Agent Authentication:* HTTP Message Signatures provide a relevant
   primitive for cryptographically authenticating selected message
   components.

   REQ-HTTP-4: An agent authentication profile SHOULD define how an
   agent identifier, signing key, operator identity, request freshness,
   and key-discovery mechanism are bound to a signed request.

   *Intent and Policy Signaling:* Any standardized intent or purpose
   signal MUST be treated as a declaration rather than proof of
   authorization, and SHOULD be cryptographically bound to the
   authenticated request when relied upon for policy.

   *Capability Negotiation:* HTTP-based agent protocols SHOULD reuse
   standard content negotiation and extensibility patterns rather than
   creating incompatible negotiation mechanisms for every framework.

   Long-running AI operations can exceed timeout assumptions made by
   HTTP clients, servers, gateways, and intermediaries.  A delayed
   response does not necessarily indicate server failure; it can
   indicate that an accepted task is still undergoing inference or other
   computation.

   REQ-HTTP-5: HTTP-based agent protocols SHOULD provide a machine-
   readable means to distinguish an accepted but still-processing
   operation from an unavailable, failed, or abandoned operation.

   REQ-HTTP-6: Agent interaction profiles SHOULD define whether a long-
   running operation remains bound to the original HTTP exchange or can
   transition to polling, callback, event delivery, streaming, or
   another asynchronous result-retrieval mechanism.



Park & Siddique           Expires 1 March 2027                 [Page 10]

Internet-Draft       AI Agent Internet Architecture          August 2026


   REQ-HTTP-7: When intermediaries are involved, agent protocols SHOULD
   NOT depend on an indefinitely open HTTP request unless expected
   timeout behavior and connection-liveness requirements are compatible
   across the path.

   REQ-HTTP-8: Retry semantics for long-running operations MUST address
   duplicate execution.  A client that loses a connection while an agent
   task continues remotely MUST be able to determine whether the
   original operation is still executing before blindly repeating a
   consequential request.

10.  Transport and Connection Continuity for Long-Running Agent
     Operations

   AI-agent workloads introduce a transport pattern in which relatively
   short request bursts can be followed by long periods of application
   silence while a model performs inference, reasoning, retrieval, tool
   execution, or coordination.  This document refers to this condition
   as inference-induced transport idleness.

   Inference-induced transport idleness does not necessarily mean that
   the endpoint, transport connection, or agent task has failed.  It
   indicates that application processing time is significantly longer
   than the interval between ordinary network exchanges.

   For TCP, a connection can remain established during such an interval.
   However, TCP congestion-control state reflects knowledge about
   network conditions rather than application task state.  After a
   sufficiently long idle period, previously measured available capacity
   can no longer necessarily be assumed to remain valid.  TCP mechanisms
   can therefore restart or revalidate transmission conservatively when
   application traffic resumes [RFC5681] [RFC7661].

   This distinction is particularly relevant when a small agent request
   triggers lengthy computation followed by a large response.  From the
   application's perspective, this can be a single continuous operation.
   From the transport's perspective, the response can follow a
   substantial idle or application-limited period.  The sender can
   consequently need to rebuild or revalidate its usable congestion
   window before transmitting the complete response.

   Connection continuity can also be affected by stateful
   infrastructure.  NATs, firewalls, proxies, gateways, and load
   balancers can discard idle flow or request state before model
   processing completes.  Application-level request timers can expire
   independently of TCP connection state.  Conversely, a transport
   connection can disappear while the remote agent task remains valid
   and continues execution.



Park & Siddique           Expires 1 March 2027                 [Page 11]

Internet-Draft       AI Agent Internet Architecture          August 2026


   Similar considerations apply to transports other than TCP.  QUIC
   defines an idle timeout and permits use of ack-eliciting packets when
   an endpoint needs to defer an idle timeout [RFC9000].  Agent
   protocols therefore SHOULD NOT assume that keeping an application
   task active automatically keeps the underlying transport association
   active.

   The architecture should distinguish transport liveness from task
   liveness.

   REQ-TRANS-1: Agent protocols MUST NOT interpret absence of
   application response data during a model-processing interval as
   sufficient evidence that the remote task has failed.

   REQ-TRANS-2: Agent interaction protocols SHOULD provide a machine-
   readable indication that a request has been accepted and remains in
   progress when processing can exceed ordinary connection or request
   timeout intervals.

   REQ-TRANS-3: Long-running agent operations SHOULD be recoverable
   across transport connection loss where the semantics of the operation
   permit recovery.

   REQ-TRANS-4: A reconnecting client SHOULD be able to correlate a new
   transport connection with an existing agent task without requiring
   the task to be executed again.

   REQ-TRANS-5: Protocols supporting long-running operations SHOULD
   define task identifiers, expiration semantics, cancellation behavior,
   and result-retrieval procedures independently of the lifetime of a
   specific TCP or QUIC connection.

   REQ-TRANS-6: Implementations SHOULD avoid unnecessary keepalive
   traffic solely for preserving long-running inference operations when
   an asynchronous or resumable interaction model can provide equivalent
   semantics.

   REQ-TRANS-7: Where transport or application keepalive mechanisms are
   used, their frequency SHOULD account for endpoint and middlebox
   timeout behavior while avoiding excessive network traffic and
   resource consumption.

   REQ-TRANS-8: Agent protocols SHOULD allow endpoints to communicate
   expected processing characteristics, where useful, without requiring
   disclosure of private reasoning traces or internal model state.






Park & Siddique           Expires 1 March 2027                 [Page 12]

Internet-Draft       AI Agent Internet Architecture          August 2026


   REQ-TRANS-9: Transport optimizations for inference-induced idle
   periods MUST preserve congestion-control safety.  An agent protocol
   MUST NOT assume that previously available path capacity remains valid
   solely because the application-level task has remained active.

   REQ-TRANS-10: Architecture and implementations SHOULD minimize the
   latency penalty associated with resuming large result transfers after
   long processing intervals while maintaining established congestion-
   control principles.

11.  Task Lifecycle Requirements

   REQ-TASK-1: A task identifier MUST be unambiguous within its protocol
   scope and MUST NOT function as a bearer credential unless the
   protocol explicitly defines and protects it as one.

   REQ-TASK-2: Task creation, status retrieval, cancellation, and result
   retrieval MUST each have defined authentication and authorization
   semantics.

   REQ-TASK-3: Protocols MUST define the effect of retry on
   consequential task-creation operations and MUST provide idempotency
   or duplicate detection where duplicate execution would be unsafe.

   REQ-TASK-4: Protocols supporting resumable tasks MUST define task
   expiration, result retention, cancellation-race, and terminal-state
   semantics.

   REQ-TASK-5: A party retrieving a result MUST be able to verify that
   the result corresponds to the intended task and authorization
   context.

12.  Authentication, Authorization, and Delegation

   Authorization is a central gap for AI-agent use cases.  Current IETF
   work on AI Agent Authentication and Authorization applies workload
   identity and the OAuth 2.0 framework [RFC6749] to agent interactions.
   Existing mechanisms to evaluate include OAuth Token Exchange
   [RFC8693], Resource Indicators [RFC8707], and Rich Authorization
   Requests [RFC9396].

   REQ-AUTH-1: The architecture MUST distinguish agent identity from the
   identity of the human or organization on whose behalf the agent acts.

   REQ-AUTH-2: Authorization evidence MUST be audience-restricted and
   SHOULD be narrowly scoped to resources and operations.





Park & Siddique           Expires 1 March 2027                 [Page 13]

Internet-Draft       AI Agent Internet Architecture          August 2026


   REQ-AUTH-3: Multi-hop delegation SHOULD preserve the original
   principal and each authorized delegation step in verifiable form,
   while allowing privacy-preserving disclosure where intermediaries do
   not require the full chain.

   REQ-AUTH-4: Delegation SHOULD express time limits, transaction or
   value limits, context constraints, and whether re-delegation is
   permitted.

   REQ-AUTH-5: A resource server MUST be able to determine the effective
   authority applicable to the current request without trusting
   unauthenticated claims from an intermediary agent.

   REQ-AUTH-6: Delegated authority MUST be revocable or naturally short-
   lived, and revocation semantics SHOULD address active multi-agent
   chains.

   REQ-AUTH-7: Authorization for a consequential operation MUST be bound
   to the intended audience, operation, and resource, and SHOULD be
   bound to a task or transaction identifier when one exists.

   REQ-AUTH-8: Re-delegation MUST NOT increase the effective authority
   received from an upstream principal.

   REQ-AUTH-9: A Resource Server MUST define how it calculates effective
   authority when a request contains multiple credentials, delegation
   steps, or policy constraints.  Failure to validate a required step
   MUST NOT result in broader authority.

   REQ-AUTH-10: Cryptographic validity of a request MUST NOT be treated
   as proof that the request reflects the current intent of the
   Delegating Principal or that the Credential Holder is uncompromised.

13.  TLS, PKI, Workload Identity, and Trust

   TLS protects channels and authenticates endpoints, but an agentic
   system can require additional bindings among endpoint identity,
   workload identity, agent identity, operator, and delegating
   principal.

   REQ-ID-1: Agent identity SHOULD be verifiably bound to a key or
   workload identity that supports rotation and short lifetimes.

   REQ-ID-2: The architecture SHOULD support proof that an agent is
   authorized to represent a domain or organization.

   REQ-ID-3: Endpoint authentication and agent authentication SHOULD be
   independently verifiable where they represent different principals.



Park & Siddique           Expires 1 March 2027                 [Page 14]

Internet-Draft       AI Agent Internet Architecture          August 2026


   REQ-ID-4: Trust decisions MUST NOT be inferred solely from successful
   authentication.

   REQ-ID-5: Designs SHOULD avoid globally stable identifiers when a
   scoped or pairwise identifier can satisfy the use case.

   REQ-ID-6: When a relying party's policy depends on the software
   composition, configuration, or execution environment of an agent, the
   architecture SHOULD support associating the authenticated agent
   identity with fresh, independently verifiable Evidence or Attestation
   Results concerning the relevant execution environment.  Such
   mechanisms SHOULD be compatible with platform-neutral remote
   attestation architectures such as [RFC9334] and SHOULD NOT require a
   universal hardware, runtime, or attestation mechanism.  Standard
   claims formats such as the Entity Attestation Token (EAT) [RFC9711]
   can be used where appropriate.

14.  Asynchronous Agent Communication

   Long-running research, procurement, orchestration, and offline
   workflows do not always fit synchronous HTTP request/response.
   Current individual proposals explore asynchronous store-and-forward
   semantics for agents.

   Long-running model execution also illustrates why asynchronous
   communication is an architectural requirement rather than merely an
   application convenience.  Keeping a transport connection open
   throughout an unpredictable inference or reasoning interval can
   consume endpoint and intermediary state, can interact poorly with
   request and idle timeouts, and can require keepalive traffic that
   provides no application value.

   An agent protocol SHOULD therefore be able to transition from a
   synchronous request/wait/response model to a request/task-accepted/
   task-identifier/processing/result-notification-or-retrieval model
   without losing authorization, delegation, transaction, provenance, or
   audit context.

   REQ-MSG-1: An asynchronous agent messaging mechanism SHOULD support
   globally unique message identifiers, correlation identifiers,
   expiration, retry, delivery status, and duplicate detection.

   REQ-MSG-2: It SHOULD provide end-to-end integrity and SHOULD allow
   confidentiality independent of relay hops.

   REQ-MSG-3: Relay infrastructure MUST be able to apply abuse controls
   without requiring access to unnecessary private task content.




Park & Siddique           Expires 1 March 2027                 [Page 15]

Internet-Draft       AI Agent Internet Architecture          August 2026


   REQ-MSG-4: The mechanism SHOULD define how authorization and
   delegation evidence is carried or referenced across delayed delivery.

   REQ-MSG-5: The IETF should first evaluate whether profiles of
   existing HTTP, messaging, event, or mail technologies can meet these
   requirements before defining a new transport.

   REQ-MSG-6: An asynchronous result MUST be correlatable with the
   request and authorization context that initiated the task.

   REQ-MSG-7: Transitioning from synchronous to asynchronous operation
   SHOULD NOT require re-execution of the original task.

   REQ-MSG-8: The architecture SHOULD permit a long-running task to
   outlive any individual transport connection used to create, observe,
   or retrieve the task.

15.  Capability and Intent-Based Resolution

   AI-agent systems add a resolution problem above IP routing: selecting
   a service or agent because it can satisfy a requested capability
   under policy constraints.  This is service selection and resolution
   at a higher layer, not a replacement for IP routing.

   REQ-CAP-1: Capability identifiers SHOULD have stable semantics
   independent of a single vendor or agent framework.

   REQ-CAP-2: Capability descriptions SHOULD be separable from endpoint
   location.

   REQ-CAP-3: Query and matching mechanisms SHOULD support constraints
   such as language, protocol, security profile, jurisdiction, price,
   latency, and policy.

   REQ-CAP-4: Ranking and reputation information MUST NOT be treated as
   authoritative identity or authorization evidence.

   REQ-CAP-5: Intent-based discovery SHOULD minimize disclosure because
   the query itself can reveal sensitive user goals.

16.  Payment and Economic Interaction

   Autonomous agents can purchase API calls, data, compute, content,
   reservations, or other services.  Payment must compose with
   discovery, authorization, spending policy, identity, and audit rather
   than exist as an isolated wallet operation.





Park & Siddique           Expires 1 March 2027                 [Page 16]

Internet-Draft       AI Agent Internet Architecture          August 2026


   REQ-PAY-1: A principal MUST be able to constrain an agent's spending
   by amount, currency or asset class, recipient or category, time, and
   transaction type.

   REQ-PAY-2: A payment proof SHOULD be bound to the resource request
   sufficiently to prevent replay for a different resource or amount.

   REQ-PAY-3: The protocol architecture SHOULD permit multiple payment
   schemes and SHOULD NOT require a particular blockchain or settlement
   network.

   REQ-PAY-4: Services SHOULD provide machine-readable receipts that can
   be correlated with authorization and audit records.

17.  Provenance, Auditability, and Accountability

   Agent actions can have financial, operational, legal, or security
   consequences.  Protocols should preserve evidence of consequential
   actions without requiring disclosure of model chain-of-thought or
   unnecessary private content.

   REQ-AUD-1: Audit evidence SHOULD support correlation of agent
   identity, operator or accountable principal, authorization context,
   request identifier, timestamp, material policy constraints, result
   status, and payment reference when applicable.

   REQ-AUD-2: Audit evidence SHOULD be tamper-evident and SHOULD support
   selective disclosure.

   REQ-AUD-3: Protocols MUST NOT require collection of private reasoning
   traces as a condition of accountability.

   REQ-AUD-4: Audit identifiers SHOULD be scoped to reduce cross-service
   tracking.

   REQ-AUD-5: Audit evidence SHOULD be able to identify or reference the
   Attestation Results, Verifier, appraisal policy, and relevant
   Reference Values that informed a trust decision when such information
   is material to that decision.  Such auditability SHOULD NOT require
   disclosure of private agent reasoning, sensitive Evidence, or
   unrelated workload data.

   REQ-AUD-6: When a policy decision is material to a consequential
   action, audit evidence SHOULD identify the policy or policy version
   used for that decision.






Park & Siddique           Expires 1 March 2027                 [Page 17]

Internet-Draft       AI Agent Internet Architecture          August 2026


   REQ-AUD-7: Audit evidence MUST distinguish an observed event from an
   assertion about that event and SHOULD identify the issuer of each
   material assertion.

   REQ-AUD-8: Tamper-evident evidence MUST NOT be treated as proof that
   the recorded action was authorized, benign, or produced by
   uncompromised software.

18.  Revocation, Suspension, and Emergency Control

   Autonomy and machine-speed execution make revocation a first-order
   protocol requirement.

   REQ-REV-1: Credentials and delegated authority SHOULD support short
   validity periods and explicit revocation where risk requires it.

   REQ-REV-2: Revocation of a parent delegation SHOULD invalidate or
   constrain dependent re-delegations according to explicit semantics.

   REQ-REV-3: Services SHOULD support rapid suspension of compromised
   agents or keys without requiring deletion of historical audit
   evidence.

   REQ-REV-4: Emergency controls SHOULD be fail-safe and SHOULD avoid a
   single globally privileged kill switch.

   REQ-REV-5: A protocol MUST define the effect of credential or
   delegation revocation separately for proposed, accepted, executing,
   and completed tasks.

   REQ-REV-6: Revocation and suspension mechanisms SHOULD bound the
   period during which stale authorization or status information can be
   accepted.

19.  Security Considerations

   Agent protocols combine authenticated machine-speed actions,
   delegation, discovery, asynchronous execution, and potentially
   financial or operational consequences.  They therefore create
   security risks even when each underlying protocol is used correctly.











Park & Siddique           Expires 1 March 2027                 [Page 18]

Internet-Draft       AI Agent Internet Architecture          August 2026


19.1.  Identity and Execution Integrity

   Possession of a valid credential establishes control of that
   credential; it does not establish that the expected software caused
   an action or that the action reflects the Delegating Principal's
   intent.  A compromised Agent Instance can generate cryptographically
   valid requests and tamper-evident logs.  Implementations MUST NOT
   treat authentication, authorization, attestation, and audit evidence
   as interchangeable trust signals.

   Where software composition, configuration, or execution state is
   relevant, a Relying Party SHOULD use fresh, independently verifiable
   Evidence or Attestation Results compatible with the RATS architecture
   [RFC9334].  EAT [RFC9711] is one standard claims format.  Attestation
   is not proof of model correctness, benign intent, or authorization.

19.2.  Confused Deputies and Delegation Amplification

   An agent that holds authority for multiple principals or resources
   can become a confused deputy.  Authorization evidence SHOULD be
   audience-, resource-, operation-, and context-restricted.  Re-
   delegation MUST attenuate rather than amplify authority.

19.3.  Replay, Retry, and Duplicate Execution

   Connection loss and asynchronous task execution make blind retry
   unsafe.  Consequential task creation requires freshness protection,
   idempotency or duplicate detection, and a means to determine whether
   an earlier task was accepted.  Payment proof, authorization evidence,
   callbacks, task results, and cancellation requests require replay
   protection appropriate to their semantics.

19.4.  Discovery and Negotiation Attacks

   Attackers can publish false capabilities, substitute endpoints,
   replay stale descriptors, suppress stronger security profiles, or
   manipulate ranking.  Discovery metadata requires authenticity,
   integrity, freshness, and downgrade protection.  Capability, ranking,
   and reputation claims MUST NOT be treated as identity or
   authorization evidence.











Park & Siddique           Expires 1 March 2027                 [Page 19]

Internet-Draft       AI Agent Internet Architecture          August 2026


19.5.  Asynchronous Relays and Callbacks

   Relays can delay, duplicate, reorder, suppress, or misdirect
   messages.  Protocols SHOULD provide end-to-end integrity and, where
   needed, confidentiality independent of relay hops.  Callback
   endpoints require authentication, authorization, request correlation,
   replay protection, and defenses against use as a server-side request-
   forgery primitive.

19.6.  Resource and Economic Exhaustion

   Agent operations can amplify small requests into expensive
   computation, tool use, messages, or payments.  Services SHOULD apply
   authenticated quotas, bounded task lifetimes, spending limits, rate
   controls, and cancellation mechanisms.  Retry policies should avoid
   amplifying failures across delegation chains.

19.7.  Revocation Races

   Revocation can occur while a task is queued or executing.  Protocol
   profiles MUST define whether revocation prevents only new tasks, also
   cancels accepted work, or affects later result retrieval.

19.8.  Evidence Limitations

   Tamper-evident evidence proves resistance to undetected modification
   under stated cryptographic assumptions.  It does not prove that an
   asserted event occurred, that an issuer was honest, or that an action
   was authorized.  Evidence consumers MUST validate issuer, freshness,
   scope, and applicable verification policy before relying on a claim.

20.  Relationship to Existing Agent Protocols

   Application-layer agent protocols and frameworks are complementary to
   the Internet mechanisms described here.  They can benefit from
   standardized discovery, authentication, delegated authorization,
   payment, and trust mechanisms.

   The architectural objective is composability: discovery identifies a
   candidate endpoint; identity authenticates it; authorization
   determines permitted actions; an interaction protocol carries the
   task; payment settles economic requirements; and provenance or audit
   mechanisms retain evidence.  No single layer should be expected to
   solve all of these functions.







Park & Siddique           Expires 1 March 2027                 [Page 20]

Internet-Draft       AI Agent Internet Architecture          August 2026


21.  Requirements and Gap Analysis

   The requirements in this document do not imply that every function
   needs a new protocol.  Existing Internet mechanisms should first be
   evaluated for profiling or composition.  New protocol work is
   justified only for residual interoperability gaps.













































Park & Siddique           Expires 1 March 2027                 [Page 21]

Internet-Draft       AI Agent Internet Architecture          August 2026


   +================+======================+===========================+
   | Function       | Existing foundations | Residual question         |
   +================+======================+===========================+
   | Naming and     | DNS, DNSSEC, SVCB/   | Common Agent              |
   | discovery      | HTTPS, Well-Known    | Descriptor semantics      |
   |                | URIs                 | and authenticated         |
   |                |                      | capability metadata       |
   +----------------+----------------------+---------------------------+
   | HTTP task      | HTTP semantics, 202  | Common lifecycle,         |
   | interaction    | Accepted, fields,    | correlation, safe         |
   |                | content negotiation  | retry, cancellation,      |
   |                |                      | and result retrieval      |
   +----------------+----------------------+---------------------------+
   | Authentication | TLS, mutual TLS,     | Bindings among            |
   |                | HTTP Message         | endpoint, service,        |
   |                | Signatures, workload | instance, operator,       |
   |                | credentials          | and credential-holder     |
   |                |                      | identities                |
   +----------------+----------------------+---------------------------+
   | Delegated      | OAuth 2.0 family,    | Bounded multi-hop re-     |
   | authorization  | token exchange,      | delegation,               |
   |                | resource indicators, | attenuation, chain        |
   |                | authorization        | validation, and           |
   |                | details              | revocation                |
   +----------------+----------------------+---------------------------+
   | Workload       | RATS and EAT         | Fresh binding between     |
   | evidence       |                      | an authenticated          |
   |                |                      | action and relevant       |
   |                |                      | Attestation Results       |
   +----------------+----------------------+---------------------------+
   | Asynchronous   | HTTP callbacks,      | Security context and      |
   | delivery       | event systems,       | task correlation          |
   |                | messaging and mail   | across delayed or         |
   |                | mechanisms           | relayed delivery          |
   +----------------+----------------------+---------------------------+
   | Audit and      | Message signatures,  | Issuer clarity,           |
   | provenance     | security-event       | minimization,             |
   |                | formats, content     | selective disclosure,     |
   |                | provenance           | and cross-domain          |
   |                | mechanisms           | correlation               |
   +----------------+----------------------+---------------------------+
   | Revocation     | Short-lived          | Effects on active         |
   |                | credentials and      | tasks and re-             |
   |                | status mechanisms    | delegation graphs         |
   +----------------+----------------------+---------------------------+

            Table 1: Existing foundations and residual questions




Park & Siddique           Expires 1 March 2027                 [Page 22]

Internet-Draft       AI Agent Internet Architecture          August 2026


   This table is architectural, not an assignment of work.  Protocol-
   specific work remains subject to the normal IETF process and the
   scope of established Working Groups.

22.  Candidate IETF Work Items

   Candidate cross-area work includes an agent identity profile; an
   OAuth-compatible multi-hop delegation profile; DNS and Well-Known
   based agent discovery profiles; a framework-neutral capability
   vocabulary and discovery metadata model; an HTTP Message Signatures
   profile for agents; authenticated intent and policy metadata; generic
   HTTP payment negotiation and receipt semantics; requirements for
   long-running agent transactions and inference-induced transport
   idleness; mechanisms for decoupling task lifetime from transport-
   connection lifetime; resumable agent transactions and task
   correlation across reconnects; asynchronous agent messaging
   requirements; privacy-preserving provenance and audit evidence;
   composition with remote attestation and attestation-result
   references; and revocation semantics for delegation chains.

   Transport-area expertise is particularly relevant in determining
   whether existing TCP, QUIC, HTTP, connection-liveness, congestion-
   control, and application-layer mechanisms adequately support AI
   workloads characterized by long processing intervals followed by
   potentially bursty or large result transfers.

   Protocol-specific wire work should remain with established expert
   Working Groups where appropriate.  Cross-area work is needed for
   common terminology, architecture, gap analysis, and composability.

23.  Current IETF Work Landscape and Coordination Gap

   As of August 2026, AI-agent-related Internet-Drafts span several
   protocol domains.  Examples include DNS for AI Discovery (DNS-AID);
   AI Agent Authentication and Authorization; Agentic AI Use Cases and
   Requirements; and individual proposals addressing agent discovery,
   invocation, transport, and authorization.

   This activity is evidence of a broad protocol problem, but it also
   exposes a coordination gap.  The drafts do not necessarily share a
   common model for agent identity, operator identity, capability
   identifiers, delegation, discovery metadata, intent, transaction
   context, or trust.  Similar functions can therefore be specified
   independently at different layers or by different communities.

   The architectural requirement is not that every proposal use the same
   wire protocol.  It is that common concepts have clear ownership and
   composable semantics.  Discovery should be able to reference an



Park & Siddique           Expires 1 March 2027                 [Page 23]

Internet-Draft       AI Agent Internet Architecture          August 2026


   authorization profile without redefining authorization; payment
   should be bindable to delegated authority without defining a new
   identity system; and agent interaction protocols should be able to
   consume common discovery and security metadata.

   A cross-IETF gap analysis and terminology effort is therefore needed
   before multiple overlapping mechanisms become widely deployed.

24.  Recommendation for IETF-Wide Coordination of AI Agent Protocol Work

   The requirements in this document cut across several existing IETF
   Areas and protocol families.  Naming and discovery touch DNS and
   Internet-area work; authentication, authorization, delegation, and
   provenance touch Security and OAuth or workload-identity work; HTTP
   semantics and messaging touch Applications and Real-Time and
   transport-related communities; transport continuity and inference-
   induced idleness touch transport and HTTP expertise; and deployment
   and lifecycle management touch Operations and Management.

   Without explicit coordination, independently developed solutions risk
   duplicating functions, defining incompatible identity or capability
   models, creating overlapping discovery mechanisms, and placing agent-
   specific semantics at inconsistent layers.  The IETF should therefore
   consider an explicit cross-area coordination activity for AI-agent-
   related Internet protocol work.  Such coordination could begin with
   common terminology, architectural principles, and a gap analysis,
   while protocol-specific extensions remain in the existing expert
   Working Groups and Areas.  The objective is not to create a
   monolithic agent protocol, but to ensure that independently developed
   mechanisms compose into a coherent Internet architecture for AI
   agents.

   As the number and scope of AI-agent-related proposals increase, the
   IETF should also consider whether a dedicated cross-area venue, or
   ultimately a new Area if the work becomes sufficiently broad and
   persistent, would improve architectural coherence, review, and
   coordination.  Any such organizational decision is outside the scope
   of this document; this document records the architectural need for
   coordinated IETF-wide treatment of the problem.

25.  Privacy Considerations

   Agent interactions can reveal a principal's goals, relationships,
   location, interests, spending constraints, organizational plans, and
   intended future actions.  Capability or intent queries can be
   sensitive even if no transaction occurs.





Park & Siddique           Expires 1 March 2027                 [Page 24]

Internet-Draft       AI Agent Internet Architecture          August 2026


   REQ-PRIV-1: Discovery and capability-resolution mechanisms SHOULD
   disclose no more intent or principal information than is necessary to
   obtain useful results.

   REQ-PRIV-2: Protocol designs SHOULD use scoped or pairwise
   identifiers when a globally stable identifier is not required.

   REQ-PRIV-3: Intermediaries SHOULD NOT receive full delegation chains,
   task contents, payment details, or attestation Evidence unless those
   values are necessary for the intermediary's function.

   REQ-PRIV-4: Audit and provenance mechanisms SHOULD support selective
   disclosure and data minimization.  Retention periods SHOULD be tied
   to a stated operational, security, or accountability purpose.

   REQ-PRIV-5: Status and result endpoints MUST prevent unauthorized
   enumeration of tasks and SHOULD avoid identifiers that enable cross-
   service correlation.

   REQ-PRIV-6: Attestation mechanisms SHOULD disclose Attestation
   Results or selectively disclosed claims instead of raw Evidence when
   those values are sufficient for the Relying Party's decision.

   Correlation can also occur through timing, endpoint selection,
   capability queries, payment metadata, and repeated security-profile
   choices even when message content is encrypted.

26.  Operational Considerations

   Task lifetime, authorization lifetime, credential lifetime, result-
   retention lifetime, transport lifetime, and audit-retention lifetime
   are independent operational values.  Deployments SHOULD document
   their relationships and avoid assuming that expiration of one
   terminates all others.

   Operators should define:

   *  Maximum accepted and executing task lifetimes;

   *  Status, result, idempotency-key, and duplicate-detection retention
      periods;

   *  Credential, delegation, discovery-metadata, and attestation
      freshness limits;

   *  Cancellation and revocation propagation objectives;





Park & Siddique           Expires 1 March 2027                 [Page 25]

Internet-Draft       AI Agent Internet Architecture          August 2026


   *  Quotas for computation, messages, callbacks, tool invocations, and
      spending;

   *  Clock-skew assumptions, key rotation, and behavior when required
      time sources are unavailable;

   *  Observability that distinguishes transport failure, task failure,
      authorization failure, and remote processing delay; and

   *  Incident procedures for compromised agents, operators, discovery
      metadata, Verifiers, and relays.

   Keepalive traffic should not substitute for resumable task semantics
   where it creates unnecessary endpoint or middlebox state.

27.  IANA Considerations

   This document has no IANA actions.

   Future protocol specifications derived from these requirements might
   request registrations for protocol elements.  Such registrations are
   outside the scope of this document.

28.  Open Issues

   1.  Which roles and lifecycle states are sufficiently common to
       standardize across agent protocols?

   2.  Can existing OAuth mechanisms express privacy-preserving,
       attenuating multi-hop delegation, or is an additional profile
       required?

   3.  Which HTTP mechanisms are sufficient for task acceptance, status,
       cancellation, idempotency, and result retrieval?

   4.  Is a common Agent Descriptor useful, and which discovery
       substrates should carry or reference it?

   5.  How should a specific agent action be bound to fresh Attestation
       Results without exposing unnecessary platform information?

   6.  How should revocation affect queued and executing tasks without
       creating unsafe partial execution?

   7.  Which gaps belong in existing Working Groups, and which require a
       cross-area venue?

29.  Normative References



Park & Siddique           Expires 1 March 2027                 [Page 26]

Internet-Draft       AI Agent Internet Architecture          August 2026


   [RFC2119]  Bradner, S., "Key words for use in RFCs to Indicate
              Requirement Levels", BCP 14, RFC 2119,
              DOI 10.17487/RFC2119, March 1997,
              <https://www.rfc-editor.org/info/rfc2119>.

   [RFC8174]  Leiba, B., "Ambiguity of Uppercase vs Lowercase in RFC
              2119 Key Words", BCP 14, RFC 8174, DOI 10.17487/RFC8174,
              May 2017, <https://www.rfc-editor.org/info/rfc8174>.

30.  Informative References

   [RFC5681]  Allman, M., Paxson, V., and E. Blanton, "TCP Congestion
              Control", RFC 5681, DOI 10.17487/RFC5681, September 2009,
              <https://www.rfc-editor.org/info/rfc5681>.

   [RFC7661]  Fairhurst, G., Sathiaseelan, A., and R. Secchi, "Updating
              TCP to Support Rate-Limited Traffic", RFC 7661,
              DOI 10.17487/RFC7661, October 2015,
              <https://www.rfc-editor.org/info/rfc7661>.

   [RFC9000]  Iyengar, J., Ed. and M. Thomson, Ed., "QUIC: A UDP-Based
              Multiplexed and Secure Transport", RFC 9000,
              DOI 10.17487/RFC9000, May 2021,
              <https://www.rfc-editor.org/info/rfc9000>.

   [RFC4033]  Arends, R., Austein, R., Larson, M., Massey, D., and S.
              Rose, "DNS Security Introduction and Requirements",
              RFC 4033, DOI 10.17487/RFC4033, March 2005,
              <https://www.rfc-editor.org/info/rfc4033>.

   [RFC6749]  Hardt, D., Ed., "The OAuth 2.0 Authorization Framework",
              RFC 6749, DOI 10.17487/RFC6749, October 2012,
              <https://www.rfc-editor.org/info/rfc6749>.

   [RFC8615]  Nottingham, M., "Well-Known Uniform Resource Identifiers
              (URIs)", RFC 8615, DOI 10.17487/RFC8615, May 2019,
              <https://www.rfc-editor.org/info/rfc8615>.

   [RFC8693]  Jones, M., Nadalin, A., Campbell, B., Ed., Bradley, J.,
              and C. Mortimore, "OAuth 2.0 Token Exchange", RFC 8693,
              DOI 10.17487/RFC8693, January 2020,
              <https://www.rfc-editor.org/info/rfc8693>.

   [RFC8707]  Campbell, B., Bradley, J., and H. Tschofenig, "Resource
              Indicators for OAuth 2.0", RFC 8707, DOI 10.17487/RFC8707,
              February 2020, <https://www.rfc-editor.org/info/rfc8707>.





Park & Siddique           Expires 1 March 2027                 [Page 27]

Internet-Draft       AI Agent Internet Architecture          August 2026


   [RFC9110]  Fielding, R., Ed., Nottingham, M., Ed., and J. Reschke,
              Ed., "HTTP Semantics", STD 97, RFC 9110,
              DOI 10.17487/RFC9110, June 2022,
              <https://www.rfc-editor.org/info/rfc9110>.

   [RFC9396]  Lodderstedt, T., Richer, J., and B. Campbell, "OAuth 2.0
              Rich Authorization Requests", RFC 9396,
              DOI 10.17487/RFC9396, May 2023,
              <https://www.rfc-editor.org/info/rfc9396>.

   [RFC9421]  Backman, A., Ed., Richer, J., Ed., and M. Sporny, "HTTP
              Message Signatures", RFC 9421, DOI 10.17487/RFC9421,
              February 2024, <https://www.rfc-editor.org/info/rfc9421>.

   [RFC9460]  Schwartz, B., Bishop, M., and E. Nygren, "Service Binding
              and Parameter Specification via the DNS (SVCB and HTTPS
              Resource Records)", RFC 9460, DOI 10.17487/RFC9460,
              November 2023, <https://www.rfc-editor.org/info/rfc9460>.

   [RFC9334]  Birkholz, H., Thaler, D., Richardson, M., Smith, N., and
              W. Pan, "Remote ATtestation procedureS (RATS)
              Architecture", RFC 9334, DOI 10.17487/RFC9334, January
              2023, <https://www.rfc-editor.org/info/rfc9334>.

   [RFC9711]  Lundblade, L., Mandyam, G., O'Donoghue, J., and C.
              Wallace, "The Entity Attestation Token (EAT)", RFC 9711,
              DOI 10.17487/RFC9711, April 2025,
              <https://www.rfc-editor.org/info/rfc9711>.

Authors' Addresses

   Soohong Daniel Park
   Samsung Electronics
   Open Source Group
   Republic of Korea
   Email: soohongp@gmail.com


   Imran Siddique
   Opaque
   United States of America
   Email: imransiddique@live.com









Park & Siddique           Expires 1 March 2027                 [Page 28]

# EvoOps — Self-Learning Autonomous Incident Response Platform

## Project Vision

EvoOps is a production-style architecture exercise and AI engineering project designed to show how an autonomous incident-response system can observe a distributed application, investigate operational failures, reason over evidence, and improve its own investigation strategies over time.

This project is not a toy chatbot or a simple prompt-demo. It is intended to model the kind of system an engineering team would build to operate a distributed platform: real services, realistic failure modes, observability, telemetry ingestion, tool-using AI agents, evaluation, and a human-in-the-loop safety model.

At a high level, the project has two connected systems:

- EvoCommerce: a simulated distributed backend where real traffic, microservice interactions, infrastructure failures, and performance issues occur.
- EvoOps: an AI-powered investigation platform that observes EvoCommerce, collects evidence, uses tools, and performs root-cause analysis with safety controls.

The end objective is not just to "generate text" about an incident, but to build an AI system that can investigate incidents using real production signals and improve over time based on measured outcomes.

---

## Problem Statement

Modern distributed systems fail in ways that are difficult to understand because symptoms are scattered across multiple layers:

- service-level latency
- database slow queries
- Redis cache errors
- message queue backlogs
- deployment regressions
- dependency timeouts
- memory leaks
- CPU saturation
- network degradation
- cascading retries and failures

When an incident happens in production, teams need to correlate metrics, logs, traces, infrastructure health, and recent changes. This is often hard because the evidence is fragmented and the investigation process is manual, noisy, and expensive.

EvoOps addresses this by creating an AI incident-response workflow that:

1. receives or detects an incident,
2. gathers evidence from the system,
3. tests hypotheses with tools,
4. produces a grounded root-cause analysis,
5. recommends remediation,
6. requires approval for risky actions,
7. records the experience,
8. learns from previous investigations,
9. adapts future strategies based on outcomes.

---

## Why This Project Exists

This project exists to demonstrate how AI can be used in production engineering in a technically credible and defensible way.

We are not trying to build a generic chatbot. We are building an application-level AI workflow with:

- observability pipelines,
- incident simulation,
- evidence-based tooling,
- structured decision-making,
- a LangGraph orchestration layer,
- memory and strategy reuse,
- evaluation and benchmarking,
- human oversight for risky actions.

The project is built to teach the following engineering disciplines together:

- distributed systems design,
- microservice communication,
- observability architecture,
- operational incident response,
- agent orchestration,
- LLM tool use,
- memory systems,
- evaluation of AI systems,
- human-in-the-loop governance,
- self-improvement loops in production AI.

---

## System Overview

The project is split into two major systems.

### System A — EvoCommerce

EvoCommerce is a simulated production backend environment that creates realistic operational behavior. It is intentionally not a customer-facing e-commerce app with a huge frontend. Instead, it is a backend simulation designed to generate real telemetry and real failure conditions.

Its purpose is to provide a realistic operating surface for EvoOps to investigate.

#### Initial service model

- API Gateway
- Order Service
- Payment Service
- Inventory Service
- Notification Service

#### Supporting infrastructure

- PostgreSQL
- Redis
- Message Queue

#### Why these services and components?

They capture the usual patterns seen in real production stacks:

- request routing through an API gateway,
- transactional business logic in an order service,
- dependency calls to payment and inventory systems,
- async notifications via a queue,
- state in relational storage,
- caching in Redis,
- queue-based processing and retries.

This is enough to produce meaningful incidents without requiring a massive full-stack application.

---

### System B — EvoOps

EvoOps is the AI layer that observes EvoCommerce, investigates incidents, and decides what to do. It is not a generic agent; it is a structured incident-response system that has explicit responsibilities.

EvoOps should eventually:

- observe metrics, logs, and traces,
- detect or receive an incident,
- build an investigation plan,
- gather evidence with tools,
- reason over multiple signals,
- generate and validate hypotheses,
- identify likely root cause,
- retrieve similar prior incidents,
- propose remediation,
- request human approval for risky actions,
- verify recovery,
- evaluate its own performance,
- update future strategy based on learning.

---

## Production-Like Architecture

The final architecture should look conceptually like this:

```text
User / Incident
    ↓
EvoOps
    ↓
Investigation Workflow
    ↓
Metrics / Logs / Traces / Database / Git / Queue / Infra Health
    ↓
Root Cause Analysis
    ↓
Recommendation
    ↓
Human Approval
    ↓
Remediation
    ↓
Verification
    ↓
Evaluation
    ↓
Experience + Strategy Memory
    ↓
Better Future Investigations
```

This flow mirrors how real incident response works in production: evidence first, reasoning second, remediation last, and learning after the fact.

---

## Observability Architecture

The platform must expose real operational signals. That is one of the core reasons EvoCommerce exists.

We want EvoOps to investigate the same evidence a production engineer would investigate.

### Signals to collect

#### Metrics

- request count
- request latency
- p50 / p95 / p99 latency
- error rate
- CPU use
- memory use
- database connection pool saturation
- database query latency
- Redis hit/miss rate
- queue depth
- queue processing time
- service availability
- downstream dependency latency

#### Logs

Structured logs should include:

- timestamp
- service name
- request ID
- trace ID
- log level
- endpoint
- error message
- stack trace details
- dependency failures
- database errors
- deployment metadata

#### Traces

Distributed tracing allows us to follow request flow across services such as:

- client
- API Gateway
- Order Service
- Payment Service
- PostgreSQL

This is crucial for understanding where delays and error propagation occur.

---

## Observability Stack

The architecture should be chosen intentionally, not blindly.

### Proposed stack

- OpenTelemetry
- OpenTelemetry Collector
- Prometheus
- Grafana
- Loki
- Tempo or Jaeger

### Why each component exists

#### OpenTelemetry

OpenTelemetry is the standard for instrumentation and telemetry collection. It gives us a consistent way to capture traces, metrics, and logs from services in a vendor-neutral way.

It matters because it allows the platform to emit signals in a structured, portable format. This is realistic and interview-relevant.

#### OpenTelemetry Collector

The collector receives telemetry from services and forwards it to backends such as Prometheus, Loki, and Tempo. It centralizes processing, batching, and export logic.

#### Prometheus

Prometheus is used for time-series metrics collection and alerting. It is the natural place to store service latency, error rates, CPU, memory, queue depth, and similar operational metrics.

#### Grafana

Grafana visualizes telemetry and provides dashboards. It allows us to build service-level, dependency-level, and incident-level views over time.

#### Loki

Loki is designed for log aggregation. It indexes labels and makes log search practical without requiring full text indexing of all content.

#### Tempo or Jaeger

Tempo/Jaeger stores distributed traces and allows us to inspect request paths and spans across services.

### Data flow

```text
Service code
   ↓
OpenTelemetry SDK
   ↓
OTel Collector
   ├── Prometheus (metrics)
   ├── Loki (logs)
   └── Tempo/Jaeger (traces)
   ↓
Grafana dashboards and EvoOps queries
```

### Why this stack is a strong fit

This combination is common in production observability stacks and demonstrates real-world engineering familiarity.

### Alternatives

Possible alternatives include:

- Jaeger instead of Tempo
- Elasticsearch + Kibana instead of Loki
- Datadog / New Relic in SaaS form
- vendor-specific monitoring stacks

We are choosing the open-source stack because it is explainable, local-first, containerizable, and realistic for a self-hosted project.

---

## Incident Generation and Fault Injection

Incidents cannot simply be "discovered naturally" in a demo environment. To evaluate EvoOps properly, we need controlled and repeatable fault injection.

The incident simulator is a core component of the project. It intentionally introduces known failures into EvoCommerce with a ground-truth model so the system can be evaluated objectively.

Each incident should be defined with:

- Incident ID
- Scenario name
- Trigger
- Fault injection mechanism
- Expected symptoms
- Affected services
- Metrics affected
- Logs generated
- Trace behavior
- Root cause
- Potential misleading symptoms
- Expected investigation path
- Expected remediation
- Risk level
- Human approval requirement
- Ground-truth resolution

This is what makes the learning loop measurable. Without known ground truth, there is no objective evaluation of investigation quality.

---

## Initial Incident Scenarios

The first set of scenarios includes the following 10:

- high_db_latency
- connection_pool_exhaustion
- redis_failure
- memory_leak
- cpu_spike
- downstream_timeout
- bad_deployment
- message_queue_backlog
- api_error_spike
- network_latency

These scenarios are intentionally chosen because they cover different failure classes and require different investigation strategies.

Examples:

### high_db_latency

- Trigger: artificial database query delay
- Expected symptoms: increasing latency, slow transaction times, downstream bottlenecks
- Root cause: database latency injected deliberately
- Misleading signal: API Gateway seems slow, but the real issue is the database layer

### connection_pool_exhaustion

- Trigger: pool saturation under load
- Expected symptoms: timeouts, request failures, connection errors
- Root cause: exhausted DB connections

### redis_failure

- Trigger: Redis unavailability or cache timeout
- Expected symptoms: increased database pressure, higher latency, partial degradation
- Misleading signal: cache miss rate appears high, but the underlying problem may be downstream database pressure

### memory_leak

- Trigger: memory growth in a service
- Expected symptoms: slowdowns, GC pressure, eventual crash or OOM

### cpu_spike

- Trigger: CPU-intensive workload or runaway process
- Expected symptoms: increased latency, dropped throughput

### downstream_timeout

- Trigger: one dependency becomes slow or unavailable
- Expected symptoms: failing requests, retries, elevated dependency latency

### bad_deployment

- Trigger: deployment with incorrect config or code regression
- Expected symptoms: sudden behavior change, failed or unstable requests

### message_queue_backlog

- Trigger: queue backlog due to slow consumer or dead-letter conditions
- Expected symptoms: delayed notifications, async processing lag

### api_error_spike

- Trigger: elevated application error rate
- Expected symptoms: 5xx spike, failed requests, traces showing specific route behavior

### network_latency

- Trigger: synthetic network delay around service-to-service communication
- Expected symptoms: multi-service latency increase, cross-dependency degradation

---

## EvoOps Investigation Model

A critical requirement is that EvoOps must investigate using tools instead of simply producing a plausible guess.

The AI system must interact with the platform using real tools such as:

- query_metrics
- query_logs
- get_trace
- get_service_health
- get_dependency_health
- get_database_metrics
- inspect_database
- get_recent_deployments
- inspect_git_commit
- search_runbooks
- search_previous_incidents
- retrieve_similar_incidents
- create_incident_report
- propose_remediation
- execute_remediation

---

## Model Context Protocol (MCP) Integration Layer

Starting in **Phase 9**, EvoOps exposes its investigation and remediation toolset through a standardized **Model Context Protocol (MCP)** server (built using FastMCP / Python MCP SDK).

```text
┌──────────────────────────────────────────────┐
│        EvoOps Investigation Agent            │
│          (LangGraph Orchestrator)            │
└──────────────────────┬───────────────────────┘
                       │
                       │ Model Context Protocol (JSON-RPC)
                       ▼
┌──────────────────────────────────────────────┐
│           EvoOps SRE MCP Server              │
├──────────────────────────────────────────────┤
│ Read-Only Tools (Auto-approved):             │
│   • query_metrics(promql)       [Prometheus] │
│   • search_logs(query, window)  [Loki]       │
│   • get_trace(trace_id)         [Tempo]      │
│   • check_service_health()      [Gateway]    │
│   • inspect_git_commit(hash)    [Git]        │
│   • search_runbooks(topic)      [Docs]       │
│                                              │
│ Action Tools (Policy & Guardrails):          │
│   • restart_service(service)    [Approval]   │
│   • rollback_deployment(rev)    [Approval]   │
│   • scale_service(replicas)     [Approval]   │
└──────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│    EvoCommerce & Observability Subsystems    │
└──────────────────────────────────────────────┘
```

### Why MCP in EvoOps?

1. **Protocol Standard:** Adopts the open industry standard for AI tool execution, allowing any MCP-compliant AI host or client (LangGraph, Claude, Antigravity, Cursor) to connect to EvoOps infrastructure seamlessly.
2. **Access Gateway & Security Perimeter:** The MCP server serves as the authorization barrier between reasoning LLMs and production infrastructure. Read-only diagnostic tools execute immediately, while disruptive actions require Human-in-the-Loop approval.
3. **Enterprise Portability:** Tools are decoupled from any specific LLM framework; the same observability tools can be invoked across various agent architectures.

---

## Tool-Based Agent Architecture

EvoOps should begin as a single capable investigation agent and grow over time.

### Early stage

A single agent with a clear investigation workflow is the correct starting point.

### Later stage

Only when there is a justified need do we introduce specialized agents such as:

- Supervisor / Orchestrator
- Incident Investigator
- Metrics Analyst
- Log Analyst
- Trace Analyst
- Deployment/Code Analyst
- Knowledge/Runbook Agent
- Validation Agent
- Remediation Agent
- Evaluator Agent

Each agent should have:

- clear responsibility,
- defined inputs,
- defined outputs,
- allowed tools,
- a reason for existing.

We should avoid agent sprawl. Complex multi-agent setups are only useful when the underlying system design justifies them.

---

## LangChain Role

LangChain should be used where it adds real engineering value, not as a gimmick.

### Appropriate responsibilities

- LLM integration
- structured outputs
- tool schemas and tool calling
- agent interface abstraction
- middleware and guardrails
- model abstraction for flexibility

### What we should avoid

- adding LangChain just for a resume line item
- wrapping everything in a vague "agent" abstraction with no real workflow
- hiding state management and orchestration behind opaque prompts

LangChain should help connect the LLM to tools and structured data, not replace the actual architecture.

---

## LangGraph Role

LangGraph should become the orchestration layer for the investigation workflow.

This is where the system should manage:

- investigation state,
- plan creation,
- conditional routing,
- evidence collection,
- hypothesis generation,
- validation,
- retries,
- human approval,
- persistence,
- operator decisions,
- recovery verification,
- multi-agent coordination when justified.

### Conceptual flow

```text
START
  ↓
Incident Analyzer
  ↓
Create Investigation Plan
  ↓
Collect Metrics
  ↓
Collect Traces
  ↓
Collect Logs
  ↓
Inspect Recent Changes
  ↓
Retrieve Similar Incidents
  ↓
Generate Hypotheses
  ↓
Validate Hypotheses
  ↓
Root cause supported?
  ├── NO → gather more evidence
  └── YES
  ↓
Generate RCA
  ↓
Generate Remediation Plan
  ↓
Human Approval
  ↓
Execute Approved Action
  ↓
Verify Recovery
  ↓
Evaluator
  ↓
Store Experience
  ↓
END
```

This graph makes the investigation process explicit and analyzable rather than burying logic in a single prompt.

---

## Memory Architecture

A self-learning AI system needs more than one memory model. In production-style systems, memory is part of the operational design.

### 1. Short-Term / Working Memory

The current investigation state.

Examples:

- active incident
- collected evidence
- active hypothesis set
- tool call history
- unresolved questions
- current confidence status

This is the ephemeral state used during a single incident.

### 2. Episodic Memory

Previous incidents and their outcomes.

Examples:

- symptoms observed
- evidence collected
- actual root cause
- remediation used
- human feedback
- success/failure status
- time to diagnosis

This memory allows EvoOps to reason from past cases.

### 3. Semantic Memory

Persistent facts about the environment.

Examples:

- service relationships
- dependency ownership
- database ownership
- runbook knowledge
- system topology
- service metadata

### 4. Procedural / Strategy Memory

Successful and failed incident-solving patterns.

Example:

- Incident type: database latency
- Successful strategy: metrics → traces → database metrics → recent deployment → logs

This stores the investigation workflow that worked previously.

### 5. Failure Memory

Past wrong assumptions.

Example:

- Previous hypothesis: Redis failure
- Actual cause: database connection exhaustion
- Lesson: do not treat cache misses as root cause without checking database utilization

This is important because learning is not just about storing success; it is also about storing false leads and course corrections.

---

## Self-Learning System

The phrase "self-learning" must be technically defensible.

We are not required to retrain a model after every incident. That would be a very different system. Instead, we implement application-level self-improvement.

The learning loop should be:

```text
Task
  ↓
Plan
  ↓
Execute
  ↓
Observe
  ↓
Evaluate
  ↓
Learn
  ↓
Store Experience
  ↓
Retrieve Experience Later
  ↓
Better Strategy
```

### What counts as learning?

The system should:

1. perform an investigation,
2. record evidence,
3. record hypotheses,
4. record decisions,
5. record root cause,
6. receive evaluation,
7. identify what worked,
8. identify what failed,
9. store successful strategies,
10. retrieve experiences in future incidents,
11. improve future investigation strategy.

This is a meaningful learning loop because it improves decision quality over time via stored operational experience rather than random prompt tweaking.

---

## Evaluation and Benchmarking

Self-learning must be measurable.

We need a benchmark with known incident scenarios and ground truth to compare:

- Before Experience Learning
- After Experience Learning

### Measurements

- root cause accuracy
- investigation success rate
- time to diagnosis
- number of unnecessary tool calls
- number of failed hypotheses
- remediation success rate
- human correction rate
- confidence calibration
- evidence coverage
- strategy reuse rate

This gives us an objective way to determine whether EvoOps is improving, not merely storing information.

---

## Human-in-the-Loop Safety Model

The system must not perform dangerous remediation without oversight.

### Approval levels

- Low risk: read-only investigation → automatic
- Medium risk: restart service → approval required
- High risk: database mutation, destructive action, broad rollback → mandatory approval

This is essential. AI should support operations, but real production systems require governance.

### Full control flow

```text
Agent recommendation
   ↓
Human approval or rejection
   ↓
Execution
   ↓
Verification
```

Human feedback should also feed back into the learning system so the platform can learn from operator corrections.

---

## Evaluator

An evaluator should independently judge the investigation.

Example checks:

- Was the root cause correct?
- Was sufficient evidence collected?
- Were tool calls appropriate?
- Were there unnecessary investigations?
- Was the conclusion grounded?
- Was remediation appropriate?
- Did remediation work?
- Did the human approve or reject appropriately?
- Was the strategy reusable?

A structured output could look like:

```json
{
  "root_cause_correct": true,
  "evidence_sufficient": true,
  "tool_efficiency": 0.84,
  "remediation_successful": true,
  "human_feedback": "approved",
  "strategy_reusable": true
}
```

This is not fake scoring; it is a real evaluation framework based on known ground truth and outcome verification.

---

## Phased Implementation Roadmap

The project is intentionally staged. We do not build all 16 phases at once. We build in layers so the architecture stays understandable and testable.

| Phase | Name | Status |
| --- | --- | --- |
| 1 | Build EvoCommerce backend | Not Started |
| 2 | Dockerize services | Not Started |
| 3 | PostgreSQL + Redis + Queue | Not Started |
| 4 | OpenTelemetry | Not Started |
| 5 | Metrics + Logs + Traces | Not Started |
| 6 | Grafana dashboards | Not Started |
| 7 | Incident Simulator | Not Started |
| 8 | Incident Scenarios | Not Started |
| 9 | EvoOps Single Agent | Not Started |
| 10 | LangGraph | Not Started |
| 11 | Specialized Agents | Not Started |
| 12 | Memory | Not Started |
| 13 | Evaluator | Not Started |
| 14 | Self-Learning Loop | Not Started |
| 15 | Human Approval + Remediation | Not Started |
| 16 | Benchmark | Not Started |

---

## Phase Details

### Phase 1 — Build EvoCommerce backend

Create the initial microservices and service-to-service interactions.

### Phase 2 — Dockerize services

Package services and infrastructure for reproducible local execution.

### Phase 3 — PostgreSQL + Redis + Queue

Add durable state, caching, and asynchronous flows.

### Phase 4 — OpenTelemetry

Instrument services for traces, metrics, and logs.

### Phase 5 — Metrics + Logs + Traces

Ensure the platform produces operational signals that EvoOps can inspect.

### Phase 6 — Grafana dashboards

Add visual operational views for service health and incidents.

### Phase 7 — Incident Simulator

Add controlled fault injection that produces known operational failures.

### Phase 8 — Incident Scenarios

Create the first 10 scenario definitions with ground truth.

### Phase 9 — EvoOps Single Agent

Build the first investigation agent and tool-calling workflow.

### Phase 10 — LangGraph

Move orchestration to a visible state-driven graph.

### Phase 11 — Specialized Agents

Add agents only where justified by workflow complexity.

### Phase 12 — Memory

Implement memory for working state, episodic history, and strategy reuse.

### Phase 13 — Evaluator

Assess whether an investigation was correct and useful.

### Phase 14 — Self-Learning Loop

Improve future investigations using prior outcomes.

### Phase 15 — Human Approval + Remediation

Add safety controls and approved remediation execution.

### Phase 16 — Benchmark

Run measured evaluations to prove learning improvement.

---

## Technology Selection Principle

We prefer technologies that:

1. solve a real problem,
2. are widely used,
3. are explainable in an interview,
4. can run locally,
5. can be containerized,
6. demonstrate AI engineering skills.

This is deliberate. We are not adding technology because it is popular or fashionable. We are adding it because it helps solve a concrete engineering problem.

### Expected stack

- Python
- FastAPI
- PostgreSQL
- Redis
- RabbitMQ or similar queue system
- OpenTelemetry
- Prometheus
- Grafana
- Loki
- Tempo or Jaeger
- Docker Compose
- LangChain
- LangGraph
- Pydantic
- SQLAlchemy or similar ORM/database access layer
- pytest for testing

---

## Local Development Model

The system should initially run locally using Docker Compose. The first objective is a reliable and reproducible local environment.

The project should eventually support something conceptually like:

```bash
docker compose up
```

We are not starting with Kubernetes. The first goal is local reliability and operational clarity.

---

## Security and Safety

Even in a simulated environment, safety matters.

We should:

- avoid destructive actions by default,
- store credentials in environment variables,
- provide a .env.example file,
- avoid hardcoded secrets,
- restrict remediation tools,
- require approval for risky operations,
- keep audit logs,
- make permissions explicit.

This ensures the AI acts like a controlled operator, not an uncontrolled automation agent.

---

## Development Principles

This project is designed around disciplined engineering principles:

- build small, understandable steps,
- explain architecture before implementation,
- validate each component before moving on,
- keep tools and permissions explicit,
- design for observability from day one,
- prefer grounded evidence over speculative reasoning,
- measure learning with objective evaluation,
- require human approval for risky actions,
- treat operational safety as a core design requirement.

---

## Repository Structure Proposal

The long-term repository structure is expected to evolve roughly like this:

```text
evoops/
├── README.md
├── docker-compose.yml
├── .env.example
├── Makefile
│
├── services/
│   ├── api-gateway/
│   ├── order-service/
│   ├── payment-service/
│   ├── inventory-service/
│   └── notification-service/
│
├── infrastructure/
│   ├── postgres/
│   ├── redis/
│   ├── rabbitmq/
│   ├── prometheus/
│   ├── grafana/
│   ├── loki/
│   ├── tempo/
│   └── otel/
│
├── incident-simulator/
│
├── evoops/
│   ├── agents/
│   ├── graph/
│   ├── tools/
│   ├── memory/
│   ├── evaluation/
│   ├── remediation/
│   └── prompts/
│
├── scenarios/
│
├── tests/
│
└── docs/
```

This structure is a long-term direction, not a requirement to create everything immediately.

---

## Quality Bar

The final project should feel like a credible engineering artifact that an AI engineer, platform engineer, or distributed systems engineer could explain in an interview.

It should demonstrate:

### Software engineering

- clean architecture
- APIs and service boundaries
- database interaction
- async processing where relevant
- testing
- error handling
- configuration
- observability

### Distributed systems

- service communication
- queues
- caching
- latency
- failure behavior
- dependency coordination
- retries
- eventual consistency where appropriate

### AI engineering

- LLM integration
- tool calling
- agent design
- LangChain usage
- LangGraph orchestration
- state management
- memory architecture
- evaluation and benchmarking
- structured outputs
- human-in-the-loop decisioning

### Production AI

- observability
- tracing
- evaluation
- failure handling
- guardrails
- auditability
- controlled autonomy
- measurable improvement

---

## Final Success Criteria

The project is considered complete only when we can demonstrate:

1. EvoCommerce runs as a distributed backend.
2. Services communicate realistically.
3. PostgreSQL, Redis, and queue infrastructure are working.
4. OpenTelemetry collects telemetry.
5. Metrics, logs, and traces are available.
6. Grafana visualizes the environment.
7. Fault injection creates known incidents.
8. At least 10 incident scenarios are reproducible.
9. EvoOps can investigate incidents using tools.
10. LangGraph manages the investigation workflow.
11. Specialized agents are introduced where justified.
12. Previous incident experiences can be retrieved.
13. An evaluator assesses investigation quality.
14. Successful and failed experiences affect future investigations.
15. Human approval controls risky remediation.
16. Approved remediation can be executed.
17. Recovery can be verified.
18. The system has a benchmark with ground truth.
19. We can compare performance before and after the learning loop.
20. The complete system can be demonstrated end-to-end.

---

## Definition of Done

The project is complete when the following are true:

- EvoCommerce is functioning as a realistic distributed backend.
- Observability is operational and visible.
- Incidents are reproducible and have ground truth.
- EvoOps uses evidence and tools instead of guessing.
- LangGraph governs the investigation workflow.
- Memory and strategy reuse are working.
- Evaluation can prove improvement over time.
- Human review controls risky actions.
- The architecture is understandable and explainable.
- The system can be demonstrated locally with Docker Compose.

---

## Development Philosophy

This project should not become "copy this code and run it." It is meant to teach:

- why the architecture looks this way,
- why services exist,
- why a queue exists,
- why Redis exists,
- why OpenTelemetry exists,
- how telemetry flows,
- how incidents propagate,
- how an agent investigates,
- how LangGraph manages state,
- how memory works,
- how evaluation works,
- how the learning loop works.

The objective is not to generate a magical demo. The objective is to build a serious engineering project that demonstrates AI in production operations.

---

## Project Roadmap & Status

| Phase | Name | Status | Description |
| :--- | :--- | :--- | :--- |
| 1 | **Build EvoCommerce backend** | **Completed** | 5 distributed FastAPI microservices communicating over HTTP |
| 2 | **Dockerize services** | **Completed** | Containerized all 5 services with Dockerfiles & Docker Compose on evonet |
| 3 | **PostgreSQL + Redis + RabbitMQ** | **Completed** | State persistence in PostgreSQL, Redis cache-aside, and async messaging with RabbitMQ |
| 4 | **OpenTelemetry** | **Completed** | Distributed tracing with OpenTelemetry SDK & Jaeger waterfall visualization across all 5 services |
| 5 | **Metrics + Logs + Traces** | **Completed** | Prometheus metrics scraping, trace-log correlation with trace_id/span_id, and log endpoint filtering |
| 6 | Grafana dashboards | Not Started | Unified observability visualization |
| 7 | Incident Simulator | Not Started | Controlled fault-injection engine for reproducible incidents |
| 8 | Incident Scenarios | Not Started | 10 known operational incident scenarios with ground truth |
| 9 | EvoOps Single Agent + MCP Server | Not Started | Investigation agent powered by FastMCP SRE tool server |
| 10 | LangGraph Orchestration | Not Started | State machine & cyclic investigation workflows |
| 11 | Specialized Agents | Not Started | Multi-agent collaboration (Metrics, Logs, Traces, Supervisor) |
| 12 | Memory Architecture | Not Started | Episodic, semantic, and procedural memory stores |
| 13 | Evaluator | Not Started | Automated diagnosis quality & grounding evaluation |
| 14 | Self-Learning Loop | Not Started | Strategy refinement based on past successful & failed investigations |
| 15 | Human Approval + Remediation | Not Started | Guardrails, human-in-the-loop approvals, and automated recovery |
| 16 | Benchmark & Verification | Not Started | Empirical evaluation: Before vs After learning comparison |


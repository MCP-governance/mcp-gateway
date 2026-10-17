# Accelerating the Adoption of Software and AI Agent Identity and Authorization (concept paper)

- Source ID: LIB-M02
- Source: https://www.nccoe.nist.gov/sites/default/files/2026-02/accelerating-the-adoption-of-software-and-ai-agent-identity-and-authorization-concept-paper.pdf
- Final URL: https://www.nccoe.nist.gov/sites/default/files/2026-02/accelerating-the-adoption-of-software-and-ai-agent-identity-and-authorization-concept-paper.pdf
- File: nccoe-agent-identity-authz-concept-paper.pdf
- SHA256: b303f7fba8c916f440a9435fa48d0e4465553f6b974d3157a1494747589e0b71
- Bytes: 406665
- Pages: 11
- Content-Type: application/pdf
- Retrieved: 2026-10-17
- Method: PDF text-layer extraction (PyMuPDF); no OCR. 표·그림·단 순서는 원본 쪽에서 확인한다. 쪽 표시는 PDF 파일의 쪽 번호다.

---

<!-- page 1 -->
 
ACCELERATING THE 
ADOPTION OF 
SOFTWARE AND AI 
AGENT IDENTITY AND 
AUTHORIZATION 
Harold Booth 
Bill Fisher 
Ryan Galluzzo 
Joshua Roberts 
National Institute of Standards and Technology 
 
 
 
 
DRAFT 
 
 
February 2026 
 
 
AI-Identity@nist.gov  
 
 
 
CONCEPT PAPER

<!-- page 2 -->
Concept Paper | Software and AI Agent Identity and Authorization 
1 
The National Cybersecurity Center of Excellence (NCCoE) at the National Institute of 
1 
Standards and Technology (NIST) addresses businesses’ most pressing cybersecurity 
2 
problems with practical, standards-based solutions using commercially available 
3 
technologies. The NCCoE collaborates with industry, academic, and government experts 
4 
to build modular, open, integrated reference designs that are broadly applicable and 
5 
repeatable. To learn more about the NCCoE, visit http://nccoe.nist.gov. To learn more 
6 
about NIST, visit http://www.nist.gov. 
7 
ABSTRACT 
8 
AI agents offer the promise of improved productivity, efficiency, and decision-making in 
9 
complex scenarios. But these benefits cannot be realized without the ability to 
10 
understand how identity principles such as identification, authentication, and 
11 
authorization can apply to agents to provide appropriate protections while enabling 
12 
business value. This concept paper seeks stakeholder input to inform a NIST National 
13 
Cybersecurity Center of Excellence (NCCoE) project focused on applying existing identity 
14 
standards and best practices to software and AI agents. Such a project would aim to 
15 
reduce implementation risk related to agentic AI by demonstrating how identity and 
16 
authorization standards and best practice can be applied to agentic architectures. 
17 
Feedback received will help determine the scope, feasibility, and potential value of the 
18 
project and inform whether a demonstration effort or other NCCoE outputs would best 
19 
address the challenge. Community input will inform subsequent project planning 
20 
activities, which could include development of a draft project description and a call for 
21 
collaborators.  
22 
KEYWORDS 
23 
authentication; authorization; identity and access management; AI; Artificial 
24 
Intelligence, Agentic AI, Software Agents, Prompt Injection. 
25 
DISCLAIMER 
26 
Certain commercial entities, equipment, products, or materials may be identified in this 
27 
document in order to describe an experimental procedure or concept adequately. Such 
28 
identification is not intended to imply recommendation or endorsement by NIST or 
29 
NCCoE, nor is it intended to imply that the entities, equipment, products, or materials 
30 
are necessarily the best available for the purpose.  
31 
While NIST and the NCCoE address goals of improving management of cybersecurity and 
32 
privacy risk through outreach and application of standards and best practices, it is the 
33 
stakeholder’s responsibility to fully perform a risk assessment to include the current 
34 
threat, vulnerabilities, likelihood of a compromise, and the impact should the threat be 
35 
realized before adopting cybersecurity measures such as this recommendation. 
36

<!-- page 3 -->
Concept Paper | Software and AI Agent Identity and Authorization 
2 
COMMENTS ON NCCOE DOCUMENTS 
37 
Individuals and organizations are encouraged to review all draft publications during 
38 
public comment periods and provide feedback. All publications from NIST’s National 
39 
Cybersecurity Center of Excellence are available at http://nccoe.nist.gov. 
40 
Comments on this publication may be submitted to: AI-Identity@nist.gov 
41 
Public comment period: February 5th, 2026 – April 2nd, 2026 
42 
All comments are subject to release under the Freedom of Information Act. 
43

<!-- page 4 -->
Concept Paper | Software and AI Agent Identity and Authorization 
3 
Note to Reviewers 
Artificial Intelligence (AI) technology brings great opportunities to organizations. Specifically, 
AI agents offer the promise of improved productivity, efficiency, and decision-making in 
complex scenarios. But these benefits cannot be realized without the ability to understand 
the security properties of deployed agents and apply appropriate controls as they access 
diverse data sets, tools, and applications to execute their mission. More specifically, 
organizations need to understand how identity principles such as identification, 
authentication, and authorization can apply to agents to provide appropriate protections 
while enabling business value.  
NIST recognizes the need to better understand these challenges as agencies and 
organizations consider adopting agentic capabilities. As such the National Cybersecurity 
Center of Excellence is considering a demonstration of how identity and authorization 
standards and best practices can be applied to AI agents. To inform its next steps, NIST is 
seeking input on the technical and operational considerations, standards and technology 
landscape, and overall scope, focus, and value of this project. In particular, NIST is interested 
in stakeholder perspectives on the following questions. These questions complement but are 
distinct from an RFI about securing AI agents issued by the Center for AI Standards and 
Innovation (CAISI) within NIST that will inform guidelines development for broader research 
agendas. Responses will be used to inform the scope, priorities and technical feasibility of a 
NCCoE demonstration project.  
1. General Questions to inform choice of Demonstration Use Case 
• What enterprise use-cases are organizations currently using agents for?   
• Which use-cases are in the near future? 
• What opportunities do agents present?  
• What risks worry you about agents? 
• What are the core characteristics of agentic architectures? 
• What support are you seeing for new protocols such as Model Context Protocol 
(MCP)? 
• In what ways do agentic architectures introduce identity and authorization 
challenges? 
o How do AI agents differ from other forms of software agents? 
o How are agentic architectures different from current microservices 
architectures? 
• What current or roadmap technology does your organization have that supports 
agents? 
• What standards exist, or are emerging, to support identity and access 
management of agents? How might these need to be adapted to support new 
security risks or paradigms introduced by AI agents?

<!-- page 5 -->
Concept Paper | Software and AI Agent Identity and Authorization 
4 
2. Identification 
• How might agents be identified in an enterprise architecture? 
o What metadata is essential for an AI agent's identity? 
o Should agent identity metadata be ephemeral (e.g. task dependent) or is it 
fixed? 
• Should agent identities be tied to specific hardware, software, or organizational 
boundaries? How would this be enforced? 
3. Authentication 
• What constitutes a strong authentication for an AI agent? 
• How do we handle key management for agents? Issuance, update, and 
revocation? 
4. Authorization  
• How can zero-trust principles be applied to agent authorization? 
• Can authorization policies be dynamically updated when an agent context 
changes?  
○ 
For example, if an agent gets access to new tools and resources, how do we 
determine sensitivity levels of data when aggregated by an agent, and 
whether users are authorized to access the aggregated response? 
• How do we establish "least privilege" for an agent, especially when its required 
actions might not be fully predictable when deployed? 
• What are the mechanisms for an agent to prove its authority to perform a specific 
action? 
• How might an agent convey the intent of its actions? 
• How do we handle delegation of authority for “on behalf of” scenarios? 
• How do we bind agent identity with human identity to support “human-in-the-
loop” authorizations? 
5. Auditing and non-repudiation 
• How can we ensure that agents log their actions and intent in a tamper-proof and 
verifiable manner?  
• How do we ensure non-repudiation for agent actions and binding back to human 
authorization? 
6. Prompt Injection prevention and mitigation 
• What controls help prevent both direct and indirect prompt injections? 
● After prompt injection occurs, what controls/practices can minimize the impact of 
the injection?  
Feel free to share your thoughts with us via AI-Identity@nist.gov by April 2nd, 2026.

<!-- page 6 -->
Concept Paper | Software and AI Agent Identity and Authorization 
5 
1. PROJECT CONCEPT 
44 
The NIST National Cybersecurity Center of Excellence is planning a project focused on 
45 
applying identity standards and best practices to AI agents. This concept paper 
46 
introduces the technical focus and scope of the proposed project, including the nature 
47 
of the challenge, the types of architectures considered, and the identity standards that 
48 
could be applied as part of this effort. NIST is seeking feedback from stakeholders and 
49 
technology collaborators on the technical reality and reasonableness of this concept and 
50 
is open to suggestions on how standards and best practices can be applied to address 
51 
this challenge.  
52 
Challenge Overview 
53 
For well over a decade, code-based systems have been used to enable automation, 
54 
cloud workloads, and the deployment of APIs. However, with the advancement of 
55 
software and AI agents—systems that have the capability for autonomous decision-
56 
making and taking action with limited human supervision to achieve complex goals—the 
57 
scale and range of actions taken by these systems has the potential to increase 
58 
exponentially. This increased scale and autonomy brings new opportunities as well as 
59 
new risks. To enable effective management of these risks and to securely capitalize on 
60 
these opportunities, enterprises and individuals need to understand how foundational 
61 
identity principles—identification, authentication, and authorization—can be applied to 
62 
ensure that agents are known, trusted, and properly governed. 
63 
 Scope 
64 
This project will focus on applying 
65 
identity standards and best 
66 
practices to agentic architectures 
67 
as depicted in Figure 1. Agentic 
68 
architectures are ones that take 
69 
in some set of instructions, 
70 
dynamically acquire additional 
71 
context from other resources 
72 
based on those instructions, 
73 
process the results, potentially 
74 
take some sort of action and 
75 
return a response. Retrieval-
76 
Augmented Generation (RAG) 
77 
and architectures using only an 
78 
LLM with its associated training 
79 
data are out of scope of our 
80 
project. Appendix A offers a 
81 
supplement flow diagram. 
82 
Figure 1. Example Agentic Architecture

<!-- page 7 -->
Concept Paper | Software and AI Agent Identity and Authorization 
6 
Areas of Interest 
83 
The areas below describe potential focus areas for exploration: 
84 
● Identification of AI and Software Systems. Leveraging existing standards, the 
85 
project will explore available means to identify software and AI agents such that 
86 
access management systems can distinguish between agent and human 
87 
identities and effectively manage the range of actions an agent may take from 
88 
controlled human-in-the-loop approval to autonomous action in response to an 
89 
input.    
90 
● Authorization of AI Systems. Leveraging standards such as OAuth 2.0 and its 
91 
extensions and policy-based access control mechanisms, to manage how rights 
92 
and entitlements are granted to software and AI agents and to enforce access 
93 
decisions based on the identity of the AI agent or software systems. 
94 
● Access Delegation. Link specific user identities to AI agents or software systems 
95 
to support effective delegation controls and maintain accountability for the 
96 
actions of automated systems.  
97 
● Logging and Transparency. Link specific AI agent and software systems actions 
98 
to the identity of the non-human entity and enable effective visibility into the 
99 
actions taken, data generated, and outcomes of automated activities within a 
100 
given system, platform, or network.  
101 
● Tracking Data Flows of an AI System. Track and maintain provenance of user 
102 
prompts and data input sources to support risk determinations and policy 
103 
decisions regarding actions to be taken by an AI Agent. 
104 
2. RELEVANT STANDARDS AND GUIDELINES 
105 
This project is currently considering the implementation of the following standards and 
106 
best practices:  
107 
● Model Context Protocol: Model Context Protocol (MCP) is a protocol that 
108 
enables AI models and agentic systems to discover, access, and interact with 
109 
external tools, data sources, and services in a consistent and structured manner. 
110 
The MCP protocol relies on existing identity standards such as Open 
111 
Authorization (OAuth) and Open ID Connect (OIDC) for rights delegation and 
112 
authentication.  
113 
● OAuth 2.0/2.1 and extensions: OAuth is an authorization standard that can be 
114 
used to support access control objectives. The standard defines a set of technical 
115 
specifications for the generation, protection, and delivery of authorization 
116 
tokens (JSON Web Tokens or JWT) to different connected endpoints (e.g., 
117 
servers). There are multiple profiles and extensions of OAuth to support specific 
118 
use cases, security properties, and features. At this time, OAuth is integrated 
119

<!-- page 8 -->
Concept Paper | Software and AI Agent Identity and Authorization 
7 
into the MCP as the primary method for authorizing agentic access. The 
120 
specification follows the draft OAuth 2.1 standard. 
121 
● OpenID Connect: OIDC is an interoperable authentication protocol based on the 
122 
OAuth 2.0 framework of specifications. Essentially, it provides a consistent way 
123 
for expressing authentication, consent, and authorization information through 
124 
identity tokens that can support access outcomes related to Agents or users 
125 
when interacting with Agents.  
126 
● SPIFFE/SPIRE: Secure Production Identity Framework for Everyone (SPIFFE) is a 
127 
framework for issuing and managing cryptographic identities to workloads and 
128 
SPIFFE Runtime Environment (SPIRE) is an implementation of SPIFFE that 
129 
provides APIs for workload attestation. Together they represent one way in 
130 
which agent workloads could be identified and authenticated.  
131 
● System for Cross-domain Identity Management: System for Cross-domain 
132 
Identity Management (SCIM) is a standard that defines RESTful APIs and JSON 
133 
schemas for automating the provisioning, deprovisioning, and lifecycle 
134 
management of identities across systems. While SCIM does not provide 
135 
authentication or authorization, it does provide a potential way to create, 
136 
update and revoke agent identities across systems.  
137 
● Next Generation Access Control: Next Generation Access Control (NGAC) is an 
138 
attribute-based access control standard that represents access control policies in 
139 
a unified graph of users, objects, attributes, and policy classes to enable fine 
140 
grained access control across a wide breadth of policies and resources. NGAC 
141 
also supports event driven policy updates, native delegation and least privilege 
142 
making it suitable for agentic systems. 
143 
NIST will also apply relevant guidelines from SP 800-207 Zero Trust Architecture, SP800-
144 
63-4 Digital Identity Guidelines, NISTIR 8587 Protecting Tokens and Assertions from 
145 
Forgery, Theft, and Misuse and other NIST guidelines as applicable.  
146 
We are open to feedback on other models, methodologies, protocols, best practices, or 
147 
standards that might address this challenge. 
148 
3. POSSIBLE USE CASES 
149 
The focus of the project will be on enterprise use-cases where greater control and 
150 
visibility can be maintained over agents and the systems they access. The challenge of 
151 
identifying and managing access for external agents from untrusted sources will not be 
152 
addressed under this initial effort, but use-cases focused on public facing or individual 
153 
agents could be addressed in future iterations of the project.  
154

<!-- page 9 -->
Concept Paper | Software and AI Agent Identity and Authorization 
8 
NIST is actively seeking feedback on real-world use cases being evaluated by agencies 
155 
and enterprises. Potential use-cases could include the following:  
156 
● Enterprise AI agents to improve work force efficiency and decision making. This 
157 
use case would focus on implementing controls to address the use of AI agents 
158 
and software to improve staff efficiency in everyday tasks (e.g., managing 
159 
calendars, assessing and creating policy documents, generating decision 
160 
recommendations). To support this use case, agents and software will need 
161 
delegated and managed access to multiple data sources to take actions based on 
162 
user prompts or inputs. 
163 
● Enterprise AI agents for security. This use case would focus on agents and 
164 
software that analyze security information and either take or recommend 
165 
security actions for an organization. As with use case #1, this will include non-
166 
human identities that access data from across a set of connected systems, but 
167 
with an elevated risk due to the sensitivity of security data. 
168 
● Enterprise AI agents for software development and deployment. This use case 
169 
would focus on automated processes for developing and deploying software and 
170 
how entitlements and authorization are supported in automated deployment 
171 
pipelines that use AI Agents. 
172 
4. DESIRED OUTCOMES 
173 
The planned NCCoE project on software and AI agent identity and authorization will 
174 
focus on producing practical, implementation-oriented guidelines to help organizations 
175 
adopt agentic capabilities while managing cybersecurity risk. Consistent with the NCCoE 
176 
mission, the ultimate deliverable will be a practice guide detailing example 
177 
implementation details built in the NCCoE laboratories using commercially available 
178 
technologies, along with key lessons learned along the way. Similar to the recent Mobile 
179 
Driver’s License project, this project intends to iteratively provide outputs that increase 
180 
awareness of the overall technology and security space related to agentic AI identity 
181 
and authorization. 
182 
Overall, this project seeks to: 
183 
● Provide a better understanding of how agents can be deployed in line with 
184 
identity and authorization standards and best practices to help agencies and 
185 
enterprise maximize value and minimize risk  
186 
● Create relationships and mechanisms to provide feedback to standards 
187 
development entities as they advance and evolve standards in the agentic 
188 
ecosystem 
189 
● Identify and communicate risks and opportunities associated with real-world 
190 
deployments of Agentic AI solutions 
191

<!-- page 10 -->
Concept Paper | Software and AI Agent Identity and Authorization 
9 
● Provide detailed implementation resources that can enable more rapid adoption 
192 
of agentic technology, consistent with risk management and organizational goals 
193 
Seeking Public Comment 
194 
The NCCoE is open to suggestions on how NCCoE resources may be able to advance the 
195 
adoption of sound security principles and best practices relating to the identification, 
196 
authentication, and authorization of AI agents. 
197 
Based upon community feedback on these topics, the NCCoE will consider instantiating 
198 
a project to engage in building an example solution using commercially available 
199 
technology. Public comments on this concept paper will help the NCCoE understand 
200 
specific challenges and needs and may be used to help define a project description.  
201 
Comments on this publication may be submitted to: AI-Identity@nist.gov 
202

<!-- page 11 -->
Concept Paper | Software and AI Agent Identity and Authorization 
10 
APPENDIX A. EXAMPLE AGENTIC ARCHITECTURE FLOW DIAGRAM 
203 
The below flow diagram offers a sequential view of how the different components of an 
204 
agentic architecture might interact. Of note is the iterative nature of the interactions 
205 
between the agent and the reasoning model (such as an LLM), where an agent may 
206 
fetch tools and resources for the reasoning model multiple times to update the model 
207 
with data, context or prompts.  
208 
 
Figure 2. Example Agentic Flow Diagram 
209

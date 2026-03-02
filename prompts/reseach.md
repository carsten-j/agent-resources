Phase 1: Research
Every meaningful task starts with a deep-read directive. I ask Claude to thoroughly understand the relevant part of the codebase before doing anything else. And I always require the findings to be written into a persistent markdown file, never just a verbal summary in the chat.

read this folder in depth, understand how it works deeply, what it does and all its specificities. when that’s done, write a detailed report of your learnings and findings in research.md

study the notification system in great details, understand the intricacies of it and write a detailed research.md document with everything there is to know about how notifications work

go through the task scheduling flow, understand it deeply and look for potential bugs. there definitely are bugs in the system as it sometimes runs tasks that should have been cancelled. keep researching the flow until you find all the bugs, don’t stop until all the bugs are found. when you’re done, write a detailed report of your findings in research.md

Notice the language: “deeply”, “in great details”, “intricacies”, “go through everything”. This isn’t fluff. Without these words, Claude will skim. It’ll read a file, see what a function does at the signature level, and move on. You need to signal that surface-level reading is not acceptable.

The written artifact (research.md) is critical. It’s not about making Claude do homework. It’s my review surface. I can read it, verify Claude actually understood the system, and correct misunderstandings before any planning happens. If the research is wrong, the plan will be wrong, and the implementation will be wrong. Garbage in, garbage out.

This is the most expensive failure mode with AI-assisted coding, and it’s not wrong syntax or bad logic. It’s implementations that work in isolation but break the surrounding system. A function that ignores an existing caching layer. A migration that doesn’t account for the ORM’s conventions. An API endpoint that duplicates logic that already exists elsewhere. The research phase prevents all of this.
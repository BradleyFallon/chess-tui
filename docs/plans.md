
use bots of different elo to generate different multiple choice options. We can keep trying with lower elo until we get a full set of unique choices which are all legal moves.

How can we test for if there are any blunder scenarios with our current move sequence. I want us to be able to define a default move sequence, so for example, let's say we do d4, Bf4, e3, Nf3... we want to analyze it. We start with d4, trivial, it is always okay, it is first move. Then we do Bf4. We should scan for in what scenarios would that be a bad move. The one that I know of is e5 from black, then we would just sacrifice our bishop for no reason. How do we scan for that? We start with move one, trivial, then move two, we check that move against the most obvious black responses. Do we just do a full on brute force? how do we generate the list of potential black responses? I suppose we could iterate through each possibility, but is that stupid? We can probably make use of exiting chess bot strategies to help figure that out.



---

with each move, put a thing in the chat that says what book openings we are in alignment with. If we can also say what defenses to expect, that too. We should have an inventory of openings and defenses and a way to check if they are applicable to the current board state. Then, later, we should be able to scroll back and review the chat/log and understand how the game developed from opening system into defense systems and when it went from book standards to rule-based. Eventually, we want to be able to ask the chat for llm advice, where the llm will get the info and be asked to advise or help write new rules etc.
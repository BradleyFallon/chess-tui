
use bots of different elo to generate different multiple choice options. We can keep trying with lower elo until we get a full set of unique choices which are all legal moves.

How can we test for if there are any blunder scenarios with our current move sequence. I want us to be able to define a default move sequence, so for example, let's say we do d4, Bf4, e3, Nf3... we want to analyze it. We start with d4, trivial, it is always okay, it is first move. Then we do Bf4. We should scan for in what scenarios would that be a bad move. The one that I know of is e5 from black, then we would just sacrifice our bishop for no reason. How do we scan for that? We start with move one, trivial, then move two, we check that move against the most obvious black responses. Do we just do a full on brute force? how do we generate the list of potential black responses? I suppose we could iterate through each possibility, but is that stupid? We can probably make use of exiting chess bot strategies to help figure that out.


put a center marker at the middle of the advantage bar.


add commands to the chat. i want to type / and then it shows a list of commands I can use with a very short description of what they mean. if the description cant fit it should be truncated with elipses and show the full thing if I hover
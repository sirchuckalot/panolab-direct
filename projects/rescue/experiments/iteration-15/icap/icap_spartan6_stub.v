`timescale 1ns/1ps
// Simulation-only primitive interface. No configuration engine is modeled.
module ICAP_SPARTAN6 (
    input wire CLK,
    input wire CE,
    input wire WRITE,
    input wire [15:0] I,
    output wire [15:0] O,
    output reg BUSY = 1'b0
);
    assign O = 16'hxxxx;
    always @(negedge CLK)
        BUSY <= !BUSY;
endmodule

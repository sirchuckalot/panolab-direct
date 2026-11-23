// External MCP acceptance fixture; NOT embedded in the ISE Docker image.
// Unconstrained generic synthesis target. NEVER PROGRAM the resulting bitstream.
module counter_top(input wire clk, input wire rst, output reg [3:0] count);
    always @(posedge clk)
        if (rst) count <= 4'b0000;
        else count <= count + 4'b0001;
endmodule

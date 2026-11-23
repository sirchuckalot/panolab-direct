// Simulation-only self-checking testbench for panolab_csr_demo.
`timescale 1ns/1ps
`default_nettype none
module panolab_csr_demo_tb;
    reg clk_i = 1'b0;
    always #5 clk_i = ~clk_i;
    reg rst_i = 1'b1;
    reg wb_cyc_i = 1'b0, wb_stb_i = 1'b0, wb_we_i = 1'b0;
    reg [3:0] wb_sel_i = 4'b0, wb_adr_i = 4'b0;
    reg [31:0] wb_dat_i = 32'b0;
    wire [31:0] wb_dat_o;
    wire wb_ack_o;
    integer checks = 0;
    panolab_csr_demo dut (.*);

    task expect_word;
        input [31:0] actual, expected;
        begin
            checks = checks + 1;
            if (actual !== expected) begin
                $display("FAIL: check=%0d actual=%08x expected=%08x", checks, actual, expected);
                $fatal(1, "CSR result mismatch");
            end
        end
    endtask

    task access;
        input request_write;
        input [3:0] address;
        input [3:0] select_bytes;
        input [31:0] write_value;
        input [31:0] expected_read;
        begin
            @(negedge clk_i);
            wb_cyc_i = 1'b1; wb_stb_i = 1'b1;
            wb_we_i = request_write; wb_adr_i = address;
            wb_sel_i = select_bytes; wb_dat_i = write_value;
            @(posedge clk_i); #1;
            expect_word({31'd0, wb_ack_o}, 32'd1);
            if (!request_write) expect_word(wb_dat_o, expected_read);
            @(negedge clk_i);
            wb_cyc_i = 1'b0; wb_stb_i = 1'b0; wb_we_i = 1'b0;
            @(posedge clk_i); #1;
            expect_word({31'd0, wb_ack_o}, 32'd0);
        end
    endtask

    initial begin
        repeat (3) @(negedge clk_i);
        rst_i = 1'b0;
        access(0, 4'h0, 4'hf, 32'h0000_0000, 32'h504c_4142);
        access(0, 4'h2, 4'hf, 32'h0000_0000, 32'h0000_0001);
        access(0, 4'h1, 4'hf, 32'h0000_0000, 32'h0000_0000);
        access(1, 4'h1, 4'hf, 32'h1122_3344, 32'h0000_0000);
        access(0, 4'h1, 4'hf, 32'h0000_0000, 32'h1122_3344);
        access(1, 4'h1, 4'b0101, 32'haabb_ccdd, 32'h0000_0000);
        access(0, 4'h1, 4'hf, 32'h0000_0000, 32'h11bb_33dd);
        access(1, 4'h1, 4'b0000, 32'hffff_ffff, 32'h0000_0000);
        access(0, 4'h1, 4'hf, 32'h0000_0000, 32'h11bb_33dd);
        access(1, 4'h0, 4'hf, 32'hffff_ffff, 32'h0000_0000);
        access(0, 4'h0, 4'hf, 32'h0000_0000, 32'h504c_4142);
        access(0, 4'hf, 4'hf, 32'h0000_0000, 32'h0000_0000);

        // Held STB/CYC: ACK must not recur and write must not replay.
        @(negedge clk_i);
        wb_cyc_i=1'b1; wb_stb_i=1'b1; wb_we_i=1'b1;
        wb_adr_i=4'h1; wb_sel_i=4'hf; wb_dat_i=32'hcafe_f00d;
        @(posedge clk_i); #1;
        expect_word({31'd0, wb_ack_o}, 32'd1);
        repeat(4) begin
            @(negedge clk_i); wb_dat_i=32'hdead_beef;
            @(posedge clk_i); #1;
            expect_word({31'd0, wb_ack_o}, 32'd0);
        end
        @(negedge clk_i); wb_cyc_i=1'b0; wb_stb_i=1'b0;
        @(posedge clk_i); #1;
        access(0, 4'h1, 4'hf, 32'h0000_0000, 32'hcafe_f00d);

        // Hardware reset must clear scratch and handshake.
        @(negedge clk_i); rst_i=1'b1;
        @(posedge clk_i); #1;
        expect_word({31'd0, wb_ack_o}, 32'd0);
        @(negedge clk_i); rst_i=1'b0;
        access(0, 4'h1, 4'hf, 32'h0000_0000, 32'h0000_0000);
        $display("PANOLAB_AGENT_RTL_PASS checks=%0d", checks);
        $finish;
    end
    initial begin
        #5000;
        $fatal(1, "Timed out waiting for classic bus response");
    end
endmodule
`default_nettype wire

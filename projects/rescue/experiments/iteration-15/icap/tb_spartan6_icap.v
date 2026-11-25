`timescale 1ns/1ps
module tb_spartan6_icap;
    reg clk = 0;
    reg reset = 1;
    reg arm = 0;
    reg start = 0;
    wire ready, active, done;

    spartan6_icap #(
        .TARGET(24'h12a53c),
        .FALLBACK(24'h96e147),
        .READ_OPCODE(8'h0b)
    ) dut (.clk(clk), .reset(reset), .arm(arm), .start(start),
           .ready(ready), .active(active), .done(done));

    always #10 clk = !clk;

    reg [15:0] expected [0:13];
    integer writes = 0;
    reg expect_write = 0;

    always @(posedge clk) begin
        if (dut.icap.CE !== !expect_write)
            $fatal(1, "Unexpected CE at %0t, write count %0d", $time, writes);
        if (expect_write) begin
            if (writes >= 14 || dut.icap.WRITE !== 1'b0 ||
                dut.icap.I !== expected[writes])
                $fatal(1, "Write %0d: got %h, expected %h, WRITE=%b",
                       writes, dut.icap.I, expected[writes], dut.icap.WRITE);
            writes = writes + 1;
        end
    end

    task tick;
        input expected_ready, expected_active, expected_done;
        begin
            @(posedge clk);
            #1;
            if ({ready, active, done} !== {expected_ready, expected_active, expected_done})
                $fatal(1, "Status at %0t: got %b%b%b, expected %b%b%b",
                       $time, ready, active, done, expected_ready, expected_active, expected_done);
            @(negedge clk);
        end
    endtask

    integer cycle;
    initial begin
        expected[0]  = 16'hffff;
        expected[1]  = 16'h5599;
        expected[2]  = 16'haa66;
        expected[3]  = 16'h4c86;
        expected[4]  = 16'ha53c;
        expected[5]  = 16'h4c81;
        expected[6]  = 16'hd048;
        expected[7]  = 16'h4c85;
        expected[8]  = 16'h87e2;
        expected[9]  = 16'h4c83;
        expected[10] = 16'hd069;
        expected[11] = 16'h0c85;
        expected[12] = 16'h0070;
        expected[13] = 16'h0400;

        tick(0, 0, 0);
        reset = 0;
        start = 1;
        tick(0, 0, 0);
        arm = 1;
        repeat (3) tick(0, 0, 0);
        start = 0;
        tick(1, 0, 0);
        arm = 0;
        tick(0, 0, 0);
        arm = 1;
        start = 1;
        tick(0, 0, 0);
        start = 0;
        tick(1, 0, 0);
        start = 1;
        tick(0, 1, 0); // Acceptance edge does not write.
        expect_write = 1;
        tick(0, 1, 0);
        tick(0, 1, 0);

        reset = 1;
        expect_write = 0;
        tick(0, 0, 0); // Reset suppresses the next write.
        if (writes != 2)
            $fatal(1, "Expected two writes before reset");
        writes = 0;
        reset = 0;
        tick(0, 0, 0); // Held start across reset cannot trigger.
        start = 0;
        tick(1, 0, 0);
        start = 1;
        tick(0, 1, 0);
        arm = 0; // Acceptance commits the full sequence.
        expect_write = 1;
        for (cycle = 0; cycle < 13; cycle = cycle + 1)
            tick(0, 1, 0);
        tick(0, 0, 1);
        expect_write = 0;

        arm = 1;
        repeat (3) tick(0, 0, 1);
        start = 0;
        tick(0, 0, 1);
        start = 1;
        tick(0, 0, 1);
        if (writes != 14)
            $fatal(1, "Expected 14 writes");
        reset = 1;
        tick(0, 0, 0);

        $display("PASS: ICAP sequence, wire order, timing, reset, and one-shot");
        $finish;
    end

    initial begin
        #2000;
        $fatal(1, "Test timed out");
    end
endmodule

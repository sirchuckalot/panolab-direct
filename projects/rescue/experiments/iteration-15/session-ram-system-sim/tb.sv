`timescale 1ns/1ps

module tb;
    reg clk125 = 0;
    reg rst_n = 0;
    reg user_btn_n;
    wire flash_clk, flash_cs_n, flash_mosi, flash_miso;
    wire eth_mdio;
    reg [7:0] rx_data=0;
    reg rx_dv=0;
    wire [7:0] tx_data;
    wire tx_en,gtx;
    reg [7:0] request [0:1199];
    reg [15:0] lengths [0:12];
    integer tx_file;
    integer tx_bytes=0, tx_frames=0;
    reg last_tx=0;
    initial begin
        tx_file=$fopen("tx.hex","w");
        $readmemh("lengths.hex",lengths);
        if (!$test$plusargs("no_upload")) begin
        #500ms;
        for(integer q=0;q<13;q=q+1) begin
            $readmemh($sformatf("request%0d.hex",q),request,0,int'(lengths[q])-1);
            for(integer i=0;i<int'(lengths[q]);i=i+1) begin
                @(negedge clk125);rx_dv=1;rx_data=request[i];
            end
            @(negedge clk125);rx_dv=0;rx_data=0;
            $display("[sim] injected request %0d",q+1);
            wait(tx_frames==q+1);
            #100us;
        end
        #10ms;
        $display("[sim] completed all thirteen exchanges");
        $fclose(tx_file); $finish;
        end
    end
    always @(posedge gtx) begin
        if(tx_en) begin $fdisplay(tx_file,"%02x",tx_data);tx_bytes<=tx_bytes+1;end
        if(last_tx && !tx_en) begin $fdisplay(tx_file,"-");tx_frames<=tx_frames+1;end
        last_tx<=tx_en;
    end
    integer duration_ms = 100;
    integer uart_bytes = 0;
    integer jedec_commands = 0;

    always #4 clk125 = ~clk125;
    assign eth_mdio = 1'bz;

    pano_logic_g2 dut (
        .clk125(clk125), .rst_n(rst_n), .user_btn_n(user_btn_n),
        .serial_rx(1'b1), .serial_tx(),
        .spiflash_clk(flash_clk), .spiflash_cs_n(flash_cs_n),
        .spiflash_miso(flash_miso), .spiflash_mosi(flash_mosi),
        .eth_clocks_rx(clk125), .eth_clocks_tx(clk125), .eth_clocks_gtx(gtx),
        .eth_col(1'b0), .eth_crs(1'b0), .eth_int_n(1'b1),
        .eth_mdc(), .eth_mdio(eth_mdio), .eth_rst_n(),
        .eth_rx_data(rx_data), .eth_rx_dv(rx_dv), .eth_rx_er(1'b0),
        .eth_tx_data(tx_data), .eth_tx_en(tx_en), .eth_tx_er()
    );

    // Mode 0. Capture MOSI on rising SCK and update MISO on falling SCK.
    // Default unsupported test chip; +known_flash selects profile JEDEC ID.
    reg [23:0] jedec_id;
    reg [7:0] flash_command = 0;
    integer flash_bits = 0;
    reg miso_bit = 1;
    reg blank_flash;
    assign flash_miso = blank_flash || flash_cs_n || miso_bit;

    always @(posedge flash_clk or posedge flash_cs_n)
        if (flash_cs_n) begin
            flash_bits <= 0;
            flash_command <= 0;
        end else begin
            if (flash_bits < 8) begin
                flash_command <= {flash_command[6:0], flash_mosi};
                if (flash_bits == 7 && !(({flash_command[6:0], flash_mosi} == 8'h9f) || ({flash_command[6:0], flash_mosi} == 8'h05))) $fatal(1, "Unexpected flash opcode");
                if (flash_bits == 7 && {flash_command[6:0], flash_mosi} == 8'h9f)
                    jedec_commands <= jedec_commands + 1;
            end
            flash_bits <= flash_bits + 1;
        end

    always @(negedge flash_clk or posedge flash_cs_n)
        if (!flash_cs_n && flash_command == 8'h05 && flash_bits >= 8 && flash_bits < 16)
            miso_bit <= 0;
        else if (!flash_cs_n && flash_command == 8'h9f && flash_bits >= 8 && flash_bits < 32)
            miso_bit <= jedec_id[31 - flash_bits];
        else
            miso_bit <= 1;

    always @(posedge dut.sys_clk)
        if (!dut.sys_rst && dut.rescuesoc_uart_core_tx_fifo_wrport_we) begin
            $write("%c", dut.rescuesoc_uart_core_tx_fifo_wrport_dat_w[7:0]);
            uart_bytes <= uart_bytes + 1;
        end

    initial begin
        user_btn_n = !$test$plusargs("button");
        blank_flash = $test$plusargs("blank_flash");
        jedec_id = $test$plusargs("real_profile") ? 24'h202018 : $test$plusargs("known_flash") ? 24'h7f1234 : 24'hef4018;
        if ($value$plusargs("ms=%d", duration_ms) && duration_ms <= 0)
            $fatal(1, "+ms must be positive");
        #200 rst_n = 1;
        #(duration_ms * 1ms);
        $display("\n[sim] UART bytes=%0d JEDEC commands=%0d sys_rst=%b",
                 uart_bytes, jedec_commands, dut.sys_rst);
        if (uart_bytes == 0) $fatal(1, "No UART bytes");
        $display("[sim] TX bytes=%0d frames=%0d",tx_bytes,tx_frames); $fclose(tx_file);
        $finish;
    end
endmodule

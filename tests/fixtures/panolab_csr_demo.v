// PanoLab Direct lab demonstration: simple classic Wishbone-like CSR responder.
// This is simulation-only proof of an agent-directed RTL workflow.
// NOT a LiteX/Etherbone integration or Pano Logic G2 hardware implementation.
`timescale 1ns/1ps
`default_nettype none
module panolab_csr_demo (
    input  wire        clk_i,
    input  wire        rst_i,
    input  wire        wb_cyc_i,
    input  wire        wb_stb_i,
    input  wire        wb_we_i,
    input  wire [3:0]  wb_sel_i,
    input  wire [3:0]  wb_adr_i,  // Word address; 0=ID, 1=scratch, 2=status
    input  wire [31:0] wb_dat_i,
    output reg  [31:0] wb_dat_o,
    output reg         wb_ack_o
);
    localparam [31:0] LAB_ID = 32'h504c_4142; // ASCII "PLAB"
    reg [31:0] scratch;
    reg served;

    // Classic single-operation transfers: the master lowers STB or CYC
    // between transactions. Once served, a held request cannot replay.
    always @(posedge clk_i) begin
        if (rst_i) begin
            scratch <= 32'b0;
            wb_dat_o <= 32'b0;
            wb_ack_o <= 1'b0;
            served <= 1'b0;
        end else begin
            wb_ack_o <= 1'b0;
            if (!wb_cyc_i || !wb_stb_i) begin
                served <= 1'b0;
            end else if (!served) begin
                served <= 1'b1;
                wb_ack_o <= 1'b1;
                case (wb_adr_i)
                    4'h0: wb_dat_o <= LAB_ID; // Read-only identity
                    4'h1: begin
                        wb_dat_o <= scratch;
                        if (wb_we_i) begin
                            if (wb_sel_i[0]) scratch[7:0] <= wb_dat_i[7:0];
                            if (wb_sel_i[1]) scratch[15:8] <= wb_dat_i[15:8];
                            if (wb_sel_i[2]) scratch[23:16] <= wb_dat_i[23:16];
                            if (wb_sel_i[3]) scratch[31:24] <= wb_dat_i[31:24];
                        end
                    end
                    4'h2: wb_dat_o <= 32'h0000_0001; // Lab ready
                    default: wb_dat_o <= 32'b0; // Reserved/invalid
                endcase
            end
        end
    end
endmodule
`default_nettype wire

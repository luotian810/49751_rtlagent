module RefModule(input clk, input reset, input en, input bit_in, output reg match);
  reg [2:0] history;
  integer filled;
  always @(posedge clk) begin
    if(reset) begin history<=0;filled<=0;match<=0;end
    else begin
      match<=en && filled>=2 && history[1:0]==2'b10 && bit_in;
      if(en) begin
        history<={history[1:0],bit_in};
        if(filled<3) filled<=filled+1;
      end
    end
  end
endmodule

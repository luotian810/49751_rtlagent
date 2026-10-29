module RefModule(input clock_i,input reset_i,input bit_enable_i,
 input bit_i,output reg match_o);
 reg [2:0] history;
 reg [1:0] seen;
 always @(posedge clock_i) begin
   if(reset_i) begin history<=0;seen<=0;match_o<=0;end
   else begin
     match_o<=0;
     if(bit_enable_i) begin
       match_o<=(seen==3 && history==3'b110 && bit_i);
       history<={history[1:0],bit_i};
       if(seen<3) seen<=seen+1'b1;
     end
   end
 end
endmodule

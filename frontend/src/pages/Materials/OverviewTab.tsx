import React, { useEffect, useState, useMemo } from 'react';
import { 
  Package, 
  ArrowRightCircle, 
  ArrowLeftCircle, 
  AlertTriangle, 
  Truck, 
  ShieldAlert, 
  TrendingDown, 
  CheckCircle2, 
  Plus, 
  Send, 
  X, 
  Clock, 
  Building2, 
  Boxes,
  SlidersHorizontal,
  Save,
  Check
} from 'lucide-react';
import { cn } from '@/utils/utils';

export interface StoreStockItem {
  id: string;
  materialName: string;
  category: string;
  unit: string;
  totalIn: number;
  totalOut: number;
  currentStock: number;
  minThreshold: number;
  unitPrice: number;
  lastIssuedTo: string;
  lastMovementTime: string;
}

const INITIAL_STORE_STOCK: StoreStockItem[] = [
  {
    id: 'STK-01',
    materialName: 'UltraTech OPC 53 Grade Cement',
    category: 'Cement Bags',
    unit: 'Bags',
    totalIn: 500,
    totalOut: 320,
    currentStock: 180,
    minThreshold: 100,
    unitPrice: 385,
    lastIssuedTo: 'Tower-B 4th Floor Slab (Contractor: Shapoorji)',
    lastMovementTime: '10:45 AM Today'
  },
  {
    id: 'STK-02',
    materialName: 'Tata Tiscon 550D TMT Rebar (16mm)',
    category: 'Steel Bundles',
    unit: 'MT',
    totalIn: 28.5,
    totalOut: 18.2,
    currentStock: 10.3,
    minThreshold: 5.0,
    unitPrice: 58500,
    lastIssuedTo: 'Basement-2 Retaining Wall (Contractor: L&T Infra)',
    lastMovementTime: '11:15 AM Today'
  },
  {
    id: 'STK-03',
    materialName: 'Heavy Duty Cuplock Scaffolding Sets',
    category: 'Heavy Equipment',
    unit: 'Sets',
    totalIn: 120,
    totalOut: 95,
    currentStock: 25,
    minThreshold: 30, // Low stock alert triggered
    unitPrice: 4200,
    lastIssuedTo: 'Tower-A External Plastering (Sub-contractor: Apex)',
    lastMovementTime: 'Yesterday 04:30 PM'
  },
  {
    id: 'STK-04',
    materialName: 'River Sand (Coarse Aggregate)',
    category: 'Cartons / Boxes',
    unit: 'Ton',
    totalIn: 42.0,
    totalOut: 26.0,
    currentStock: 16.0,
    minThreshold: 10.0,
    unitPrice: 1850,
    lastIssuedTo: 'Tower-C Blockwork Masonry',
    lastMovementTime: '02:00 PM Today'
  },
  {
    id: 'STK-05',
    materialName: 'Finolex Schedule 40 UPVC Pipes 4"',
    category: 'Pipes',
    unit: 'Lengths',
    totalIn: 250,
    totalOut: 190,
    currentStock: 60,
    minThreshold: 50,
    unitPrice: 890,
    lastIssuedTo: 'Tower-A Plumbing & Drainage Shaft',
    lastMovementTime: '12:30 PM Today'
  },
  {
    id: 'STK-06',
    materialName: 'Kajaria Vitrified Floor Tiles (600x600)',
    category: 'Tiles',
    unit: 'Boxes',
    totalIn: 600,
    totalOut: 450,
    currentStock: 150,
    minThreshold: 100,
    unitPrice: 650,
    lastIssuedTo: 'Tower-B 1st to 3rd Floor Finishing',
    lastMovementTime: '03:10 PM Today'
  }
];

export default function OverviewTab() {
  const [stockItems, setStockItems] = useState<StoreStockItem[]>(() => {
    const saved = localStorage.getItem('hero_store_stock');
    return saved ? JSON.parse(saved) : INITIAL_STORE_STOCK;
  });

  const [showOutwardModal, setShowOutwardModal] = useState<boolean>(false);
  const [editingItem, setEditingItem] = useState<StoreStockItem | null>(null);
  const [newThreshold, setNewThreshold] = useState<number>(0);

  const [outwardForm, setOutwardForm] = useState({
    stockId: 'STK-01',
    quantity: 50,
    issuedTo: 'Tower-A Slab Casting (Contractor: Hero Civil)',
    vehicleNumber: 'HR26 DK 8921',
    issuedBy: 'Store Supervisor Ritesh'
  });

  // Calculate Aggregates
  const totalInVal = useMemo(() => stockItems.reduce((acc, s) => acc + s.totalIn, 0), [stockItems]);
  const totalOutVal = useMemo(() => stockItems.reduce((acc, s) => acc + s.totalOut, 0), [stockItems]);
  const currentStockVal = useMemo(() => stockItems.reduce((acc, s) => acc + s.currentStock, 0), [stockItems]);
  const lowStockCount = useMemo(() => stockItems.filter(s => s.currentStock <= s.minThreshold).length, [stockItems]);
  const totalStockValuation = useMemo(() => stockItems.reduce((acc, s) => acc + (s.currentStock * s.unitPrice), 0), [stockItems]);

  const handleIssueOutward = (e: React.FormEvent) => {
    e.preventDefault();
    const item = stockItems.find(s => s.id === outwardForm.stockId);
    if (!item) return;

    if (outwardForm.quantity > item.currentStock) {
      alert(`⚠️ Insufficient Stock! Only ${item.currentStock} ${item.unit} available in store.`);
      return;
    }

    const updated = stockItems.map(s => {
      if (s.id === outwardForm.stockId) {
        const newOut = Number(s.totalOut) + Number(outwardForm.quantity);
        const newStock = Number(s.currentStock) - Number(outwardForm.quantity);
        return {
          ...s,
          totalOut: newOut,
          currentStock: newStock,
          lastIssuedTo: outwardForm.issuedTo,
          lastMovementTime: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' Today'
        };
      }
      return s;
    });

    setStockItems(updated);
    localStorage.setItem('hero_store_stock', JSON.stringify(updated));
    setShowOutwardModal(false);

    alert(`✅ Outbound Gate-Pass Generated!\n\nMaterial: ${item.materialName}\nQuantity Issued: ${outwardForm.quantity} ${item.unit}\nIssued To: ${outwardForm.issuedTo}\nVehicle Plate: ${outwardForm.vehicleNumber.toUpperCase()}\nRemaining Store Balance: ${item.currentStock - outwardForm.quantity} ${item.unit}`);
  };

  const handleSaveThreshold = (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingItem) return;

    const updated = stockItems.map(s => {
      if (s.id === editingItem.id) {
        return { ...s, minThreshold: Number(newThreshold) };
      }
      return s;
    });

    setStockItems(updated);
    localStorage.setItem('hero_store_stock', JSON.stringify(updated));
    setEditingItem(null);
  };

  return (
    <div className="space-y-6 text-slate-900">
      {/* Top Metric Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat 
          icon={Package} 
          label="Total Inward Received" 
          value={totalInVal.toLocaleString()} 
          sublabel="All site consignments"
          tone="bg-blue-50 border-blue-200 text-blue-600" 
        />
        <Stat 
          icon={ArrowLeftCircle} 
          label="Total Outward Issued" 
          value={totalOutVal.toLocaleString()} 
          sublabel="Consumed in towers/work"
          tone="bg-indigo-50 border-indigo-200 text-indigo-600" 
        />
        <Stat 
          icon={Boxes} 
          label="Current Store Stock Balance" 
          value={currentStockVal.toLocaleString()} 
          sublabel={`Valuation: ₹${totalStockValuation.toLocaleString('en-IN')}`}
          tone="bg-emerald-50 border-emerald-200 text-emerald-600" 
        />
        <Stat 
          icon={ShieldAlert} 
          label="Low Stock / Re-order Warnings" 
          value={String(lowStockCount)} 
          sublabel={lowStockCount > 0 ? "Items below safety threshold" : "All stocks healthy ✅"}
          tone={lowStockCount > 0 ? "bg-amber-50 border-amber-200 text-amber-600" : "bg-emerald-50 border-emerald-200 text-emerald-600"} 
        />
      </div>

      {/* Live Store Inventory & Stock Balance Table */}
      <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
          <div>
            <h3 className="text-lg font-bold text-slate-900 tracking-wide flex items-center gap-2">
              <Boxes className="w-5 h-5 text-emerald-600" /> Live Store Stock &amp; Inventory Balance
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Real-time Inward (Received) vs Outward (Issued to site) calculation with safety threshold monitoring
            </p>
          </div>

          <button
            onClick={() => setShowOutwardModal(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-bold text-xs shadow-md shadow-blue-500/20 active:scale-95 transition-all w-fit cursor-pointer"
          >
            <Truck className="w-4 h-4" /> 🚚 Issue Outward Gate-Pass
          </button>
        </div>

        {/* Table */}
        <div className="overflow-x-auto custom-scrollbar">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 text-[11px] font-bold text-slate-500 uppercase tracking-wider bg-slate-50/70">
                <th className="py-3 px-4">Material Name &amp; Category</th>
                <th className="py-3 px-3 text-right">Total In (Received)</th>
                <th className="py-3 px-3 text-right">Total Out (Issued)</th>
                <th className="py-3 px-3 text-right">Current Stock in Store</th>
                <th className="py-3 px-3 text-center">Stock Health &amp; Buffer</th>
                <th className="py-3 px-4">Last Issued / Consumed At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-xs">
              {stockItems.map((item) => {
                const isLow = item.currentStock <= item.minThreshold;
                const percent = Math.min(100, Math.round((item.currentStock / item.totalIn) * 100));

                return (
                  <tr key={item.id} className="hover:bg-slate-50/80 transition-colors group">
                    <td className="py-3 px-4">
                      <div className="font-semibold text-slate-900 group-hover:text-blue-600 transition-colors">{item.materialName}</div>
                      <div className="text-[10px] text-slate-500">{item.category} • Ref: {item.id}</div>
                    </td>
                    <td className="py-3 px-3 text-right font-mono font-bold text-blue-600">
                      +{item.totalIn} <span className="text-[10px] font-normal text-slate-500">{item.unit}</span>
                    </td>
                    <td className="py-3 px-3 text-right font-mono font-bold text-indigo-600">
                      -{item.totalOut} <span className="text-[10px] font-normal text-slate-500">{item.unit}</span>
                    </td>
                    <td className="py-3 px-3 text-right font-mono font-bold text-sm text-slate-900">
                      {item.currentStock} <span className="text-[10px] font-normal text-slate-500">{item.unit}</span>
                      <div className="text-[10px] text-slate-500 font-normal mt-0.5">₹{(item.currentStock * item.unitPrice).toLocaleString('en-IN')}</div>
                    </td>
                    <td className="py-3 px-3 text-center">
                      <div className="flex flex-col items-center gap-1">
                        {isLow ? (
                          <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-600 border border-rose-200 flex items-center justify-center gap-1 mx-auto w-fit">
                            <AlertTriangle className="w-3 h-3" /> Low Stock ({percent}%)
                          </span>
                        ) : (
                          <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-600 border border-emerald-200 flex items-center justify-center gap-1 mx-auto w-fit">
                            <CheckCircle2 className="w-3 h-3" /> Optimal ({percent}%)
                          </span>
                        )}
                        <button
                          type="button"
                          onClick={() => {
                            setEditingItem(item);
                            setNewThreshold(item.minThreshold);
                          }}
                          className="text-[10px] text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1 hover:underline cursor-pointer bg-blue-50/60 px-2 py-0.5 rounded border border-blue-100"
                          title="Click to change Minimum Safety Buffer Threshold"
                        >
                          <SlidersHorizontal className="w-2.5 h-2.5" /> Buffer: {item.minThreshold} {item.unit} (Edit)
                        </button>
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <div className="text-slate-800 text-[11px] font-medium truncate max-w-[280px]">{item.lastIssuedTo}</div>
                      <div className="text-[10px] text-slate-500 flex items-center gap-1 mt-0.5">
                        <Clock className="w-3 h-3 text-slate-400" /> {item.lastMovementTime}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Edit Safety Buffer Threshold Modal */}
      {editingItem && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4" onClick={() => setEditingItem(null)}>
          <div className="bg-white border border-slate-200 shadow-2xl rounded-2xl max-w-md w-full p-6 space-y-4 text-slate-900" onClick={e => e.stopPropagation()}>
            <div className="flex items-start justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-blue-50 text-blue-600 border border-blue-200">
                  <SlidersHorizontal className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900">Set Safety Buffer Threshold</h3>
                  <p className="text-xs text-slate-500">Configure re-order warning level</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setEditingItem(null)}
                className="text-slate-400 hover:text-slate-700 p-1 rounded-md cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSaveThreshold} className="space-y-4">
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-1">
                <div className="text-xs font-semibold text-slate-600">Material</div>
                <div className="text-sm font-bold text-slate-900">{editingItem.materialName}</div>
                <div className="text-xs text-slate-500 flex justify-between pt-1 border-t border-slate-200">
                  <span>Current In Store: <strong className="text-slate-900">{editingItem.currentStock} {editingItem.unit}</strong></span>
                  <span>Total Received: <strong className="text-slate-900">{editingItem.totalIn} {editingItem.unit}</strong></span>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                  Minimum Safety Threshold ({editingItem.unit})
                </label>
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={newThreshold}
                  onChange={e => setNewThreshold(Number(e.target.value))}
                  className="w-full bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2.5 text-sm font-bold text-slate-900 focus:ring-2 focus:ring-primary/40 focus:border-primary outline-none"
                  required
                />
                <p className="text-[11px] text-slate-500 mt-1">
                  💡 If stock drops to or below <strong className="text-slate-700">{newThreshold} {editingItem.unit}</strong>, the system will trigger a <strong>Low Stock Alert</strong>.
                </p>
              </div>

              {/* Real-time Preview */}
              <div className="p-3 rounded-xl border text-xs flex items-center justify-between"
                   style={{
                     backgroundColor: editingItem.currentStock <= newThreshold ? '#FEF2F2' : '#F0FDF4',
                     borderColor: editingItem.currentStock <= newThreshold ? '#FECACA' : '#BBF7D0',
                     color: editingItem.currentStock <= newThreshold ? '#B91C1C' : '#15803D'
                   }}>
                <span className="font-semibold">Projected Status:</span>
                <span className="font-bold flex items-center gap-1">
                  {editingItem.currentStock <= newThreshold ? (
                    <>⚠️ Low Stock Warning</>
                  ) : (
                    <>✅ Optimal / Healthy</>
                  )}
                </span>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setEditingItem(null)}
                  className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold text-xs transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs shadow-md shadow-blue-600/20 active:scale-95 transition-all flex items-center gap-1.5 cursor-pointer"
                >
                  <Save className="w-3.5 h-3.5" /> Save Buffer Threshold
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Outward Issue Gate-Pass Modal */}
      {showOutwardModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4 text-slate-900 relative">
            <div className="flex items-start justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-blue-50 border border-blue-200 text-blue-600">
                  <Truck className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900">Issue Material Outward (Gate Pass)</h3>
                  <p className="text-xs text-slate-500">Release material from central store to construction site / contractor</p>
                </div>
              </div>
              <button
                onClick={() => setShowOutwardModal(false)}
                className="text-slate-400 hover:text-slate-700 p-1 rounded-md cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleIssueOutward} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Select Material from Store</label>
                <select
                  value={outwardForm.stockId}
                  onChange={e => setOutwardForm({ ...outwardForm, stockId: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2.5 text-xs text-slate-900 outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
                >
                  {stockItems.map(s => (
                    <option key={s.id} value={s.id}>
                      {s.materialName} (Available Stock: {s.currentStock} {s.unit})
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Quantity to Issue</label>
                  <input
                    type="number"
                    min="1"
                    value={outwardForm.quantity}
                    onChange={e => setOutwardForm({ ...outwardForm, quantity: Number(e.target.value) })}
                    className="w-full bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2 text-xs text-slate-900 outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Transport Vehicle / Tractor</label>
                  <input
                    type="text"
                    value={outwardForm.vehicleNumber}
                    onChange={e => setOutwardForm({ ...outwardForm, vehicleNumber: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2 text-xs text-slate-900 uppercase font-mono outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Issued To / Purpose / Contractor</label>
                <input
                  type="text"
                  value={outwardForm.issuedTo}
                  onChange={e => setOutwardForm({ ...outwardForm, issuedTo: e.target.value })}
                  placeholder="e.g. Tower-B 4th Floor Slab (Shapoorji)"
                  className="w-full bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2 text-xs text-slate-900 outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
                  required
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowOutwardModal(false)}
                  className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold text-xs cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-bold text-xs shadow-md shadow-blue-500/20 active:scale-95 transition-all flex items-center gap-1.5 cursor-pointer"
                >
                  <Send className="w-3.5 h-3.5" /> Issue Gate-Pass &amp; Update Stock
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ icon: Icon, label, value, sublabel, tone }: { icon: any; label: string; value: string; sublabel: string; tone: string }) {
  return (
    <div className={cn('border rounded-2xl p-5 flex flex-col justify-between shadow-xs relative overflow-hidden bg-white', tone)}>
      <div className="flex items-start justify-between mb-2">
        <div className={cn('p-2.5 rounded-xl w-fit shadow-xs', tone)}>
          <Icon className="w-5 h-5" />
        </div>
        <span className="text-[10px] uppercase font-bold tracking-wider opacity-80">{label}</span>
      </div>
      <div>
        <div className="text-3xl font-black leading-tight text-slate-900 mb-0.5">{value}</div>
        <div className="text-[11px] font-medium text-slate-500">{sublabel}</div>
      </div>
    </div>
  );
}

